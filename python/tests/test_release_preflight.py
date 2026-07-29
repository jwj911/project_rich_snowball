"""生产发布预检核心与 CLI 的聚焦回归。"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import release_preflight as release_cli
from services.release_preflight import (
    CheckCode,
    CheckStatus,
    ReleasePreflightInput,
    redact_sensitive_text,
    run_release_preflight,
)

DATABASE_PASSWORD = "database-password-should-not-leak"
REDIS_PASSWORD = "redis-password-should-not-leak"
SECRET_KEY = "release-secret-key-with-at-least-32-characters"
PROVIDER_TOKEN = "provider-token-should-not-leak"
INVALID_GATE_CASES = (
    ("ENV", "staging", CheckCode.ENV_PRODUCTION),
    ("DATABASE_URL", "sqlite:///production.db", CheckCode.DATABASE_POSTGRESQL),
    ("SECRET_KEY", "too-short", CheckCode.SECRET_KEY_STRONG),
    ("CORS_ORIGINS", "http://app.example.com", CheckCode.CORS_ORIGINS_SECURE),
    ("DATA_SOURCE", "mock", CheckCode.DATA_SOURCE_REAL),
    ("REDIS_URL", "", CheckCode.REDIS_URL_CONFIGURED),
    ("RELEASE_COMMIT", "", CheckCode.RELEASE_COMMIT_PRESENT),
    ("RELEASE_WINDOW_UTC", "2026-07-30T10:00:00+08:00", CheckCode.RELEASE_WINDOW_UTC),
    ("RELEASE_OWNER", "", CheckCode.RELEASE_OWNER_PRESENT),
    ("ROLLBACK_OWNER", "", CheckCode.ROLLBACK_OWNER_PRESENT),
    ("SSE_DEPLOYMENT_MODE", "multi", CheckCode.SSE_DEPLOYMENT_MODE_SUPPORTED),
)


def _valid_values() -> dict[str, str]:
    return {
        "ENV": "production",
        "DATABASE_URL": f"postgresql+psycopg://release:{DATABASE_PASSWORD}@db.example.com/releases",
        "SECRET_KEY": SECRET_KEY,
        "CORS_ORIGINS": "https://app.example.com,https://api.example.com:8443",
        "DATA_SOURCE": "tushare",
        "REDIS_URL": f"redis://release:{REDIS_PASSWORD}@redis.example.com:6379/0",
        "RELEASE_COMMIT": "0123456789abcdef0123456789abcdef01234567",
        "RELEASE_WINDOW_UTC": "2026-07-30T02:00:00Z/2026-07-30T03:00:00+00:00",
        "RELEASE_OWNER": "release-oncall",
        "ROLLBACK_OWNER": "rollback-oncall",
        "SSE_DEPLOYMENT_MODE": "sticky",
        "TUSHARE_TOKEN": PROVIDER_TOKEN,
    }


def test_all_release_gates_pass_with_stable_codes_and_trace_id():
    report = run_release_preflight(
        _valid_values(),
        trace_id="f" * 32,
        now=datetime(2026, 7, 29, 23, 30, tzinfo=UTC),
    )

    assert report.passed is True
    assert [check.code for check in report.checks] == list(CheckCode)
    assert all(check.status is CheckStatus.PASSED for check in report.checks)

    payload = report.to_dict()
    assert payload["trace_id"] == "f" * 32
    assert payload["generated_at"] == "2026-07-29T23:30:00Z"
    assert payload["status"] == "passed"
    assert payload["summary"] == {"total": 11, "passed": 11, "failed": 0}
    assert payload["metadata"] == {
        "release_commit": "0123456789abcdef0123456789abcdef01234567",
        "release_window_utc": "2026-07-30T02:00:00Z/2026-07-30T03:00:00Z",
    }


def test_each_release_preflight_run_has_an_independent_trace_id():
    first_report = run_release_preflight(_valid_values())
    second_report = run_release_preflight(_valid_values())

    assert first_report.trace_id != second_report.trace_id
    assert len(first_report.trace_id) == len(second_report.trace_id) == 32


@pytest.mark.parametrize(
    ("key", "value", "expected_code"),
    INVALID_GATE_CASES,
)
def test_each_release_gate_has_a_stable_failure_code(key: str, value: str, expected_code: CheckCode):
    values = _valid_values()
    values[key] = value

    report = run_release_preflight(values)

    assert report.passed is False
    assert [check.code for check in report.checks if check.status is CheckStatus.FAILED] == [expected_code]


@pytest.mark.parametrize(("key", "value", "expected_code"), INVALID_GATE_CASES)
def test_each_release_gate_cli_failure_is_traceable_and_fully_redacted(
    key: str,
    value: str,
    expected_code: CheckCode,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
):
    environment = _valid_values()
    environment.update(
        {
            "AUDIT_DATABASE_PASSWORD": DATABASE_PASSWORD,
            "AUDIT_REDIS_PASSWORD": REDIS_PASSWORD,
            "AUDIT_PROVIDER_TOKEN": PROVIDER_TOKEN,
            "AUDIT_SECRET": SECRET_KEY,
        }
    )
    environment["RELEASE_COMMIT"] = (
        f"candidate-{DATABASE_PASSWORD}-{REDIS_PASSWORD}-{SECRET_KEY}-{PROVIDER_TOKEN}"
    )
    environment[key] = value
    report_path = tmp_path / f"{expected_code.value}.json"

    exit_code = release_cli.main(["--report-path", str(report_path)], environ=environment)

    captured = capsys.readouterr()
    stdout = json.loads(captured.out)
    written = json.loads(report_path.read_text(encoding="utf-8"))
    failed_codes = [check["code"] for check in written["checks"] if check["status"] == "failed"]
    all_output = captured.out + captured.err + caplog.text + report_path.read_text(encoding="utf-8")

    assert exit_code == release_cli.EXIT_GATE_FAILED
    assert captured.err == ""
    assert stdout == written
    assert stdout["trace_id"] == written["trace_id"]
    assert len(written["trace_id"]) == 32
    assert failed_codes == [expected_code.value]
    for secret in (DATABASE_PASSWORD, REDIS_PASSWORD, SECRET_KEY, PROVIDER_TOKEN):
        assert secret not in all_output


@pytest.mark.parametrize(
    "origin",
    [
        "https://*.example.com",
        "http://app.example.com",
        "https://localhost",
        "https://api.localhost",
        "https://127.0.0.2",
        "https://[::1]",
        "https://user:password@app.example.com",
        "https://app.example.com/path",
    ],
)
def test_cors_rejects_wildcards_local_and_non_origin_urls(origin: str):
    values = _valid_values()
    values["CORS_ORIGINS"] = origin

    report = run_release_preflight(values)

    cors_check = next(check for check in report.checks if check.code is CheckCode.CORS_ORIGINS_SECURE)
    assert cors_check.status is CheckStatus.FAILED


def test_allow_origins_fallback_and_supported_single_mode_pass():
    values = _valid_values()
    values.pop("CORS_ORIGINS")
    values["ALLOW_ORIGINS"] = "https://app.example.com/"
    values["SSE_DEPLOYMENT_MODE"] = "single"

    assert run_release_preflight(values).passed is True


@pytest.mark.parametrize(
    "window",
    [
        "",
        "2026-07-30",
        "2026-07-30T02:00:00",
        "2026-07-30T10:00:00+08:00",
        "2026-07-30T03:00:00Z/2026-07-30T02:00:00Z",
        "2026-07-30T02:00:00Z/invalid",
    ],
)
def test_release_window_requires_valid_utc_time_or_ordered_interval(window: str):
    values = _valid_values()
    values["RELEASE_WINDOW_UTC"] = window

    report = run_release_preflight(values)

    window_check = next(check for check in report.checks if check.code is CheckCode.RELEASE_WINDOW_UTC)
    assert window_check.status is CheckStatus.FAILED
    assert report.to_dict()["metadata"]["release_window_utc"] is None


def test_report_and_redaction_never_expose_credentials_or_provider_tokens():
    values = _valid_values()
    values["RELEASE_COMMIT"] = f"candidate-{DATABASE_PASSWORD}-{PROVIDER_TOKEN}"
    report_text = run_release_preflight(values).to_json()
    raw_diagnostic = (
        f"DATABASE_URL=postgresql://release:{DATABASE_PASSWORD}@db.example.com/releases "
        f"TUSHARE_TOKEN={PROVIDER_TOKEN} SECRET_KEY={SECRET_KEY}"
    )
    redacted = redact_sensitive_text(raw_diagnostic, (DATABASE_PASSWORD, PROVIDER_TOKEN, SECRET_KEY))

    for secret in (DATABASE_PASSWORD, REDIS_PASSWORD, SECRET_KEY, PROVIDER_TOKEN):
        assert secret not in report_text
        assert secret not in redacted
    assert "postgresql://***@db.example.com/releases" in redacted
    assert "TUSHARE_TOKEN=***" in redacted
    assert "SECRET_KEY=***" in redacted


def test_direct_input_redacts_url_password_from_release_metadata():
    values = _valid_values()
    preflight_input = ReleasePreflightInput(
        environment=values["ENV"],
        database_url=values["DATABASE_URL"],
        secret_key=values["SECRET_KEY"],
        cors_origins=values["CORS_ORIGINS"],
        data_source=values["DATA_SOURCE"],
        redis_url=values["REDIS_URL"],
        release_commit=f"candidate-{DATABASE_PASSWORD}-{REDIS_PASSWORD}",
        release_window_utc=values["RELEASE_WINDOW_UTC"],
        release_owner=values["RELEASE_OWNER"],
        rollback_owner=values["ROLLBACK_OWNER"],
        sse_deployment_mode=values["SSE_DEPLOYMENT_MODE"],
    )

    report_text = run_release_preflight(preflight_input).to_json()

    assert DATABASE_PASSWORD not in report_text
    assert REDIS_PASSWORD not in report_text


def test_cli_arguments_override_environment_and_write_passing_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    environment = _valid_values()
    environment["ENV"] = "staging"
    report_path = tmp_path / "preflight.json"

    exit_code = release_cli.main(
        ["--env", "production", "--report-path", str(report_path)],
        environ=environment,
    )

    assert exit_code == release_cli.EXIT_PASSED
    stdout = json.loads(capsys.readouterr().out)
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert written == stdout
    assert written["status"] == "passed"
    assert written["trace_id"]


def test_cli_gate_failure_still_writes_a_traceable_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    environment = _valid_values()
    environment["RELEASE_OWNER"] = ""
    report_path = tmp_path / "failed.json"

    exit_code = release_cli.main(["--report-path", str(report_path)], environ=environment)

    assert exit_code == release_cli.EXIT_GATE_FAILED
    stdout = json.loads(capsys.readouterr().out)
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert stdout["trace_id"] == written["trace_id"]
    assert written["status"] == "failed"
    assert written["summary"]["failed"] == 1


def test_cli_gate_failure_redacts_sensitive_argument_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    leaked_password = "argument-password-should-not-leak"
    environment = _valid_values()
    environment["RELEASE_COMMIT"] = f"candidate-{leaked_password}"
    report_path = tmp_path / "failed-redacted.json"

    exit_code = release_cli.main(
        [
            "--database-url",
            f"sqlite://release:{leaked_password}@db.example.com/releases",
            "--report-path",
            str(report_path),
        ],
        environ=environment,
    )

    captured = capsys.readouterr()
    report_text = report_path.read_text(encoding="utf-8")
    assert exit_code == release_cli.EXIT_GATE_FAILED
    assert captured.err == ""
    assert leaked_password not in captured.out
    assert leaked_password not in report_text
    assert json.loads(captured.out)["trace_id"] == json.loads(report_text)["trace_id"]


def test_cli_report_write_failure_returns_two_without_leaking_inputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    environment = _valid_values()
    report_path = tmp_path / "missing" / PROVIDER_TOKEN / "preflight.json"

    exit_code = release_cli.main(["--report-path", str(report_path)], environ=environment)

    captured = capsys.readouterr()
    assert exit_code == release_cli.EXIT_REPORT_WRITE_FAILED
    assert captured.out == ""
    error = json.loads(captured.err)
    assert error["status"] == "report_write_failed"
    assert error["trace_id"]
    for secret in (DATABASE_PASSWORD, REDIS_PASSWORD, SECRET_KEY, PROVIDER_TOKEN):
        assert secret not in captured.err


def test_cli_does_not_open_database_network_or_mutate_other_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    def forbidden_operation(*args, **kwargs):
        raise AssertionError("release preflight attempted a forbidden operation")

    monkeypatch.setattr(sqlite3, "connect", forbidden_operation)
    monkeypatch.setattr(socket, "create_connection", forbidden_operation)
    report_path = tmp_path / "preflight.json"

    exit_code = release_cli.main(["--report-path", str(report_path)], environ=_valid_values())

    assert exit_code == release_cli.EXIT_PASSED
    assert [path.name for path in tmp_path.iterdir()] == ["preflight.json"]
    assert json.loads(capsys.readouterr().out)["status"] == "passed"


def test_cli_script_entrypoint_uses_environment_and_redacts_output(tmp_path: Path):
    environment = os.environ.copy()
    environment.update(_valid_values())
    report_path = tmp_path / "subprocess-report.json"
    script_path = Path(__file__).parents[1] / "scripts" / "release_preflight.py"

    result = subprocess.run(
        [sys.executable, str(script_path), "--report-path", str(report_path)],
        cwd=script_path.parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == release_cli.EXIT_PASSED, result.stderr
    assert json.loads(result.stdout)["status"] == "passed"
    assert json.loads(report_path.read_text(encoding="utf-8"))["trace_id"]
    for secret in (DATABASE_PASSWORD, REDIS_PASSWORD, SECRET_KEY, PROVIDER_TOKEN):
        assert secret not in result.stdout
        assert secret not in result.stderr
        assert secret not in report_path.read_text(encoding="utf-8")
