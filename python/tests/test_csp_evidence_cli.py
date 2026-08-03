"""R10 CSP evidence CLI safety, exit-code, and atomic-write tests."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from scripts import csp_evidence_report as cli
from services.csp_evidence import (
    CSP_EVIDENCE_REPORT_MAX_BYTES,
    CspEvidenceCounts,
    CspEvidenceProblem,
    CspEvidenceProblemCode,
    CspEvidenceReport,
    CspEvidenceStatus,
    EvidenceSource,
    WorkflowName,
)

EXPLICIT_DATABASE_URL = "postgresql://audit:explicit-db-secret@db.example.test/evidence"
ENV_DATABASE_URL = "postgresql://audit:environment-db-secret@db.example.test/evidence"
SENSITIVE_FIXTURE = "sensitive_cli_fixture_7c9479"
SENSITIVE_REPORT_BODY = "sensitive_report_body_847d31"
RAW_EXCEPTION_TEXT = "raw exception text sensitive_cli_fixture_7c9479"


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


def _context_document(
    *,
    evidence_source: str = "synthetic",
    environment: str = "ci",
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "evidence_source": evidence_source,
        "environment": environment,
        "release": "a" * 40,
        "window_start": "2026-08-01T00:00:00Z",
        "window_end": "2026-08-02T00:00:00Z",
        "sample_rate": 1,
        "complete_business_cycle": True,
        "workflows": {name.value: "passed" for name in WorkflowName},
        "metrics": {
            "business_http_requests": 1,
            "csp_outcomes": {
                "received": 1,
                "accepted": 0,
                "sampled": 1,
                "rejected": 0,
                "rate_limited": 0,
                "persist_failed": 0,
            },
        },
        "expected_document_origins": ["https://app.example.test"],
        "trusted_source_origins": ["https://static.example.test"],
    }


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def cli_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    repository = tmp_path / "repository"
    inputs = tmp_path / f"inputs-{SENSITIVE_FIXTURE}"
    output = tmp_path / f"output-{SENSITIVE_FIXTURE}"
    repository.mkdir()
    inputs.mkdir()
    output.mkdir()
    monkeypatch.setattr(cli, "REPOSITORY_ROOT", repository)

    context_path = inputs / "context.json"
    catalog_path = inputs / "catalog.json"
    _write_json(context_path, _context_document())
    _write_json(catalog_path, {"schema_version": 1, "entries": []})
    return {
        "repository": repository,
        "context": context_path,
        "catalog": catalog_path,
        "report": output / "report.json",
    }


def _arguments(paths: dict[str, Path], database_url: str | None = None) -> list[str]:
    arguments = [
        "--context-path",
        str(paths["context"]),
        "--catalog-path",
        str(paths["catalog"]),
        "--report-path",
        str(paths["report"]),
    ]
    if database_url is not None:
        arguments[:0] = ["--database-url", database_url]
    return arguments


def _report(
    context: Any,
    status: CspEvidenceStatus,
    trace_id: str,
) -> CspEvidenceReport:
    problems: tuple[CspEvidenceProblem, ...] = ()
    error_type = None
    if status is CspEvidenceStatus.INSUFFICIENT_EVIDENCE:
        problems = (CspEvidenceProblem(CspEvidenceProblemCode.SYNTHETIC_EVIDENCE, 1),)
    elif status is CspEvidenceStatus.BLOCKED:
        problems = (CspEvidenceProblem(CspEvidenceProblemCode.UNKNOWN_VIOLATION, 1),)
    elif status is CspEvidenceStatus.FAILED:
        problems = (CspEvidenceProblem(CspEvidenceProblemCode.QUERY_FAILED, 1),)
        error_type = "SyntheticCollectionError"

    return CspEvidenceReport(
        trace_id=trace_id,
        generated_at="2026-08-02T00:00:00Z",
        status=status,
        context=context,
        counts=CspEvidenceCounts(),
        checks=(),
        problems=problems,
        aggregates=(),
        known_violations=(),
        unknown_violations=(),
        metrics=None if status is CspEvidenceStatus.FAILED else context.metrics,
        error_type=error_type,
    )


def _install_collection_stub(
    monkeypatch: pytest.MonkeyPatch,
    status: CspEvidenceStatus,
) -> tuple[dict[str, Any], _FakeEngine]:
    observed: dict[str, Any] = {}
    engine = _FakeEngine()

    def fake_create_engine(database_url: str) -> _FakeEngine:
        observed["database_url"] = database_url
        return engine

    def fake_run_csp_evidence(
        bind: _FakeEngine,
        context: Any,
        catalog: Any,
        *,
        trace_id: str,
    ) -> CspEvidenceReport:
        observed["bind"] = bind
        observed["context"] = context
        observed["catalog"] = catalog
        return _report(context, status, trace_id)

    monkeypatch.setattr(cli, "create_engine", fake_create_engine)
    monkeypatch.setattr(cli, "run_csp_evidence", fake_run_csp_evidence)
    return observed, engine


def _forbid_database_access(*args: object, **kwargs: object) -> None:
    del args, kwargs
    raise AssertionError("database access occurred before CLI input validation")


def test_explicit_database_url_overrides_environment(
    cli_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed, engine = _install_collection_stub(
        monkeypatch,
        CspEvidenceStatus.INSUFFICIENT_EVIDENCE,
    )

    exit_code = cli.main(
        _arguments(cli_paths, EXPLICIT_DATABASE_URL),
        environ={"DATABASE_URL": ENV_DATABASE_URL},
    )

    captured = capsys.readouterr()
    assert exit_code == cli.EXIT_INSUFFICIENT_EVIDENCE
    assert observed["database_url"] == EXPLICIT_DATABASE_URL
    assert observed["bind"] is engine
    assert engine.disposed is True
    assert json.loads(captured.out)["status"] == "insufficient_evidence"
    assert captured.err == ""


def test_database_url_falls_back_only_to_environment(
    cli_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observed, engine = _install_collection_stub(
        monkeypatch,
        CspEvidenceStatus.INSUFFICIENT_EVIDENCE,
    )

    exit_code = cli.main(
        _arguments(cli_paths),
        environ={"DATABASE_URL": ENV_DATABASE_URL},
    )

    captured = capsys.readouterr()
    assert exit_code == cli.EXIT_INSUFFICIENT_EVIDENCE
    assert observed["database_url"] == ENV_DATABASE_URL
    assert engine.disposed is True
    assert captured.err == ""


def test_non_database_paths_are_explicitly_required_before_database_access(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(cli, "create_engine", _forbid_database_access)

    exit_code = cli.main(
        ["--database-url", EXPLICIT_DATABASE_URL],
        environ={"DATABASE_URL": ENV_DATABASE_URL},
    )

    captured = capsys.readouterr()
    assert exit_code == cli.EXIT_FAILED
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "CSP_ARGUMENT_INVALID"
    assert EXPLICIT_DATABASE_URL not in captured.err
    assert ENV_DATABASE_URL not in captured.err


@pytest.mark.parametrize(
    ("invalid_input", "expected_code"),
    [
        ("context", "CSP_CONTEXT_INVALID_JSON"),
        ("catalog", "CSP_CATALOG_INVALID_JSON"),
    ],
)
def test_invalid_inputs_are_rejected_before_database_access(
    invalid_input: str,
    expected_code: str,
    cli_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_paths[invalid_input].write_text(
        f'{{"invalid":"{SENSITIVE_FIXTURE}"',
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "create_engine", _forbid_database_access)

    exit_code = cli.main(
        _arguments(cli_paths, EXPLICIT_DATABASE_URL),
        environ={},
    )

    captured = capsys.readouterr()
    assert exit_code == cli.EXIT_FAILED
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == expected_code
    assert not cli_paths["report"].exists()
    assert SENSITIVE_FIXTURE not in captured.err
    assert EXPLICIT_DATABASE_URL not in captured.err
    assert str(cli_paths[invalid_input]) not in captured.err


def test_repository_report_path_is_rejected_before_database_access(
    cli_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_paths["report"] = cli_paths["repository"] / f"{SENSITIVE_FIXTURE}.json"
    monkeypatch.setattr(cli, "create_engine", _forbid_database_access)

    exit_code = cli.main(
        _arguments(cli_paths, EXPLICIT_DATABASE_URL),
        environ={},
    )

    captured = capsys.readouterr()
    assert exit_code == cli.EXIT_FAILED
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "CSP_REPORT_PATH_INVALID"
    assert not cli_paths["report"].exists()
    assert SENSITIVE_FIXTURE not in captured.err
    assert EXPLICIT_DATABASE_URL not in captured.err


@pytest.mark.parametrize(
    ("status", "expected_exit", "expected_stream"),
    [
        pytest.param(
            CspEvidenceStatus.INSUFFICIENT_EVIDENCE,
            cli.EXIT_INSUFFICIENT_EVIDENCE,
            "stdout",
            id="synthetic-exit-1",
        ),
        pytest.param(
            CspEvidenceStatus.READY_FOR_REVIEW,
            cli.EXIT_READY_FOR_REVIEW,
            "stdout",
            id="ready-exit-0",
        ),
        pytest.param(
            CspEvidenceStatus.BLOCKED,
            cli.EXIT_BLOCKED,
            "stdout",
            id="blocked-exit-2",
        ),
        pytest.param(
            CspEvidenceStatus.FAILED,
            cli.EXIT_FAILED,
            "stderr",
            id="failed-exit-3",
        ),
    ],
)
def test_statuses_map_to_stable_exit_codes(
    status: CspEvidenceStatus,
    expected_exit: int,
    expected_stream: str,
    cli_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    if status is CspEvidenceStatus.READY_FOR_REVIEW:
        _write_json(
            cli_paths["context"],
            _context_document(
                evidence_source="target_environment",
                environment="production",
            ),
        )
    observed, _ = _install_collection_stub(monkeypatch, status)

    exit_code = cli.main(
        _arguments(cli_paths, EXPLICIT_DATABASE_URL),
        environ={},
    )

    captured = capsys.readouterr()
    stream = captured.out if expected_stream == "stdout" else captured.err
    assert exit_code == expected_exit
    assert json.loads(stream)["status"] == status.value
    assert (captured.err == "") is (expected_stream == "stdout")
    assert (captured.out == "") is (expected_stream == "stderr")
    assert json.loads(cli_paths["report"].read_text(encoding="utf-8"))["status"] == status.value
    assert cli_paths["report"].stat().st_size <= CSP_EVIDENCE_REPORT_MAX_BYTES
    if status is CspEvidenceStatus.INSUFFICIENT_EVIDENCE:
        assert observed["context"].evidence_source is EvidenceSource.SYNTHETIC


def test_atomic_write_replaces_in_same_directory_without_partial_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    report_path = tmp_path / "report.json"
    old_payload = b'{"generation":"old"}'
    new_payload = b'{"generation":"new"}'
    report_path.write_bytes(old_payload)
    real_replace = os.replace
    observed: dict[str, Path] = {}

    def checked_replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        source_path = Path(source)
        target_path = Path(target)
        assert source_path.parent == report_path.parent
        assert target_path == report_path
        assert report_path.read_bytes() == old_payload
        assert source_path.read_bytes() == new_payload
        observed["temporary"] = source_path
        real_replace(source_path, target_path)

    monkeypatch.setattr(cli.os, "replace", checked_replace)

    cli._atomic_write(report_path, new_payload)

    assert report_path.read_bytes() == new_payload
    assert not observed["temporary"].exists()
    assert list(tmp_path.glob(".report.json.*.tmp")) == []


@pytest.mark.skipif(os.name == "nt", reason="POSIX mode bits are not enforceable on Windows")
def test_atomic_write_sets_private_mode_when_supported(tmp_path: Path) -> None:
    report_path = tmp_path / "private-report.json"

    cli._atomic_write(report_path, b"{}")

    assert stat.S_IMODE(report_path.stat().st_mode) == 0o600


class _WriteFailureFile:
    def __init__(self, raw_file: Any) -> None:
        self.raw_file = raw_file

    def __enter__(self) -> _WriteFailureFile:
        return self

    def __exit__(self, *args: object) -> None:
        self.raw_file.close()

    def write(self, payload: bytes) -> int:
        del payload
        raise OSError(RAW_EXCEPTION_TEXT)


@pytest.mark.parametrize("failure_stage", ["write", "replace", "chmod", "fsync"])
def test_report_write_failures_return_four_clean_temporary_files_and_redact_output(
    failure_stage: str,
    cli_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _install_collection_stub(monkeypatch, CspEvidenceStatus.READY_FOR_REVIEW)
    if failure_stage == "write":
        real_fdopen = cli.os.fdopen

        def failing_fdopen(descriptor: int, *args: object, **kwargs: object) -> _WriteFailureFile:
            return _WriteFailureFile(real_fdopen(descriptor, *args, **kwargs))

        monkeypatch.setattr(cli.os, "fdopen", failing_fdopen)
    elif failure_stage == "replace":
        cli_paths["report"].write_bytes(b"existing-report")

        def failing_replace(*args: object, **kwargs: object) -> None:
            del args, kwargs
            raise OSError(RAW_EXCEPTION_TEXT)

        monkeypatch.setattr(cli.os, "replace", failing_replace)
    elif failure_stage == "chmod":

        def failing_chmod(*args: object, **kwargs: object) -> None:
            del args, kwargs
            raise OSError(RAW_EXCEPTION_TEXT)

        monkeypatch.setattr(cli.os, "fchmod", failing_chmod, raising=False)
    else:

        def failing_fsync(*args: object, **kwargs: object) -> None:
            del args, kwargs
            raise OSError(RAW_EXCEPTION_TEXT)

        monkeypatch.setattr(cli.os, "fsync", failing_fsync)

    exit_code = cli.main(
        _arguments(cli_paths, EXPLICIT_DATABASE_URL),
        environ={},
    )

    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert exit_code == cli.EXIT_REPORT_WRITE_FAILED
    assert captured.out == ""
    assert error["status"] == "report_write_failed"
    assert error["code"] == "CSP_REPORT_WRITE_FAILED"
    assert error["error_type"] == "OSError"
    assert list(cli_paths["report"].parent.glob(".report.json.*.tmp")) == []
    if failure_stage == "replace":
        assert cli_paths["report"].read_bytes() == b"existing-report"
    else:
        assert not cli_paths["report"].exists()
    for prohibited in (
        EXPLICIT_DATABASE_URL,
        "explicit-db-secret",
        RAW_EXCEPTION_TEXT,
        SENSITIVE_FIXTURE,
        str(cli_paths["context"]),
        str(cli_paths["catalog"]),
        str(cli_paths["report"]),
        '"schema_version"',
        '"scope"',
    ):
        assert prohibited not in captured.err


def test_stdout_does_not_echo_database_paths_or_report_body(
    cli_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    engine = _FakeEngine()
    monkeypatch.setattr(cli, "create_engine", lambda database_url: engine)

    class ReportWithSensitiveBody:
        def __init__(self, report: CspEvidenceReport) -> None:
            self._report = report
            self.trace_id = report.trace_id
            self.status = report.status
            self.counts = report.counts
            self.error_type = report.error_type
            self.problems = report.problems

        def to_json(self) -> str:
            payload = self._report.to_dict()
            payload["test_only_body_marker"] = SENSITIVE_REPORT_BODY
            return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def fake_run(
        bind: _FakeEngine,
        context: Any,
        catalog: Any,
        *,
        trace_id: str,
    ) -> ReportWithSensitiveBody:
        del bind, catalog
        return ReportWithSensitiveBody(_report(context, CspEvidenceStatus.INSUFFICIENT_EVIDENCE, trace_id))

    monkeypatch.setattr(cli, "run_csp_evidence", fake_run)

    exit_code = cli.main(
        _arguments(cli_paths, EXPLICIT_DATABASE_URL),
        environ={"DATABASE_URL": ENV_DATABASE_URL},
    )

    captured = capsys.readouterr()
    assert exit_code == cli.EXIT_INSUFFICIENT_EVIDENCE
    assert captured.err == ""
    assert SENSITIVE_REPORT_BODY in cli_paths["report"].read_text(encoding="utf-8")
    summary = json.loads(captured.out)
    assert set(summary) == {"trace_id", "status", "counts"}
    assert summary["status"] == "insufficient_evidence"
    assert summary["counts"] == CspEvidenceCounts().to_dict()
    for prohibited in (
        EXPLICIT_DATABASE_URL,
        ENV_DATABASE_URL,
        "explicit-db-secret",
        "environment-db-secret",
        SENSITIVE_FIXTURE,
        SENSITIVE_REPORT_BODY,
        str(cli_paths["context"]),
        str(cli_paths["catalog"]),
        str(cli_paths["report"]),
        '"schema_version"',
        '"scope"',
    ):
        assert prohibited not in captured.out


def test_oversized_report_is_replaced_by_bounded_failed_report(
    cli_paths: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    engine = _FakeEngine()
    monkeypatch.setattr(cli, "create_engine", lambda database_url: engine)

    class OversizedReport:
        status = CspEvidenceStatus.READY_FOR_REVIEW
        counts = CspEvidenceCounts()
        error_type = None
        problems: tuple[CspEvidenceProblem, ...] = ()

        def __init__(self, trace_id: str) -> None:
            self.trace_id = trace_id

        def to_json(self) -> str:
            return json.dumps({"oversized": SENSITIVE_REPORT_BODY * CSP_EVIDENCE_REPORT_MAX_BYTES})

    def fake_run(
        bind: _FakeEngine,
        context: Any,
        catalog: Any,
        *,
        trace_id: str,
    ) -> OversizedReport:
        del bind, context, catalog
        return OversizedReport(trace_id)

    monkeypatch.setattr(cli, "run_csp_evidence", fake_run)

    exit_code = cli.main(
        _arguments(cli_paths, EXPLICIT_DATABASE_URL),
        environ={},
    )

    captured = capsys.readouterr()
    report_bytes = cli_paths["report"].read_bytes()
    report = json.loads(report_bytes)
    assert exit_code == cli.EXIT_FAILED
    assert captured.out == ""
    assert json.loads(captured.err)["code"] == "CSP_REPORT_SIZE_EXCEEDED"
    assert len(report_bytes) <= CSP_EVIDENCE_REPORT_MAX_BYTES
    assert report["status"] == "failed"
    assert report["problems"] == [{"code": "CSP_REPORT_SIZE_EXCEEDED", "count": 1}]
    assert SENSITIVE_REPORT_BODY.encode() not in report_bytes
    assert SENSITIVE_REPORT_BODY not in captured.err
