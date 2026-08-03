"""R9 CSP violation report ingestion and redaction tests."""

import json
import logging
import re

import pytest
from sqlalchemy import text

import routers.frontend_logs as frontend_logs_router
from config import _parse_release_commit, _parse_unit_interval, _trusted_csp_environment
from models import FrontendLogDB
from services.metrics import csp_reports_total

LEGACY_CONTENT_TYPE = "application/csp-report"
REPORTING_CONTENT_TYPE = "application/reports+json"


@pytest.fixture
def csp_db(db_session):
    db_session.execute(text("DELETE FROM frontend_logs"))
    db_session.commit()
    yield db_session
    db_session.execute(text("DELETE FROM frontend_logs"))
    db_session.commit()


def _legacy_report(**overrides):
    report = {
        "document-uri": "https://example.com/products/AU",
        "blocked-uri": "inline",
        "effective-directive": "script-src-elem",
        "violated-directive": "script-src 'self'",
        "disposition": "report",
        "line-number": 12,
        "column-number": 7,
        "status-code": 200,
    }
    report.update(overrides)
    return {"csp-report": report}


def _reporting_item(**body_overrides):
    body = {
        "documentURL": "https://example.com/products/AU",
        "blockedURL": "inline",
        "effectiveDirective": "script-src-elem",
        "disposition": "report",
        "lineNumber": 12,
        "columnNumber": 7,
        "statusCode": 200,
    }
    body.update(body_overrides)
    return {
        "type": "csp-violation",
        "age": 12,
        "url": "https://collector.invalid/ignored?token=secret",
        "body": body,
    }


def _post_json(client, payload, content_type):
    return client.post(
        "/api/log/csp-report",
        content=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": content_type},
    )


def _metric_value(outcome):
    return csp_reports_total.labels(outcome=outcome)._value.get()


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("0123456789ABCDEF0123456789ABCDEF01234567", "0123456789abcdef0123456789abcdef01234567"),
    ],
)
def test_release_commit_configuration_is_optional_and_normalized(raw_value, expected):
    assert _parse_release_commit(raw_value) == expected


@pytest.mark.parametrize(
    "raw_value",
    [
        "0" * 39,
        "0" * 41,
        ("0" * 39) + "g",
        "release-0123456789abcdef0123456789abcdef",
        f" {'0' * 40} ",
    ],
)
def test_release_commit_configuration_requires_full_hex_sha(raw_value):
    with pytest.raises(ValueError, match="RELEASE_COMMIT"):
        _parse_release_commit(raw_value)


@pytest.mark.parametrize("environment", ["development", "ci", "staging", "production"])
def test_csp_environment_accepts_only_exact_controlled_values(environment):
    assert _trusted_csp_environment(environment) == environment


@pytest.mark.parametrize("environment", [None, "", "test", "Production", " production "])
def test_csp_environment_rejects_uncontrolled_values(environment):
    assert _trusted_csp_environment(environment) is None


def test_legacy_report_is_redacted_allowlisted_and_persisted(client, csp_db, monkeypatch):
    received_before = _metric_value("received")
    accepted_before = _metric_value("accepted")
    trusted_release = "0123456789abcdef0123456789abcdef01234567"
    monkeypatch.setattr(frontend_logs_router, "CSP_REPORT_ENVIRONMENT", "production")
    monkeypatch.setattr(frontend_logs_router, "RELEASE_COMMIT", trusted_release)
    payload = _legacy_report(
        **{
            "document-uri": "https://user:password@example.com/products/AU?token=document-secret#private",
            "blocked-uri": "https://cdn-user:cdn-pass@cdn.example.com/app.js?sig=blocked-secret#source",
            "source-file": "https://source.example.com/runtime.js?token=source-secret#fragment",
            "referrer": "https://ref.example.com/start?code=referrer-secret#fragment",
            "sample": "document.cookie",
            "script-sample": "<script>secret-script</script>",
            "cookie": "session=secret-cookie",
            "authorization": "Bearer secret-authorization",
            "unknown": {"dom": "<main>secret-dom</main>"},
            "environment": "client-controlled",
            "release": "f" * 40,
        }
    )

    response = _post_json(client, payload, f"{LEGACY_CONTENT_TYPE}; charset=utf-8")

    assert response.status_code == 202
    assert response.json() == {"accepted": 1, "sampled": 0, "persist_failed": 0}
    assert "secret" not in response.text
    assert _metric_value("received") == received_before + 1
    assert _metric_value("accepted") == accepted_before + 1

    logs = csp_db.query(FrontendLogDB).all()
    assert len(logs) == 1
    log = logs[0]
    assert log.user_id is None
    assert log.log_type == "csp-violation"
    assert log.level == "warning"
    assert log.url == "https://example.com/products/AU"
    assert log.user_agent is None
    assert log.environment == "production"
    assert log.release == trusted_release

    stored = json.loads(log.payload_json)
    assert set(stored) == {
        "blocked_url",
        "column_number",
        "disposition",
        "document_url",
        "effective_directive",
        "line_number",
        "referrer",
        "source_file",
        "status_code",
        "trace_id",
        "violated_directive",
    }
    assert stored["document_url"] == "https://example.com/products/AU"
    assert stored["blocked_url"] == "https://cdn.example.com/app.js"
    assert stored["source_file"] == "https://source.example.com/runtime.js"
    assert stored["referrer"] == "https://ref.example.com/start"
    assert stored["violated_directive"] == "script-src"
    assert re.fullmatch(r"[0-9a-f]{32}", stored["trace_id"])
    assert "secret" not in log.payload_json
    assert "sample" not in stored
    assert "unknown" not in stored
    assert "environment" not in stored
    assert "release" not in stored


def test_client_attribution_is_ignored_when_server_metadata_is_unavailable(
    client,
    csp_db,
    monkeypatch,
):
    monkeypatch.setattr(frontend_logs_router, "CSP_REPORT_ENVIRONMENT", None)
    monkeypatch.setattr(frontend_logs_router, "RELEASE_COMMIT", None)
    payload = _legacy_report(environment="production", release="f" * 40)

    response = _post_json(client, payload, LEGACY_CONTENT_TYPE)

    assert response.status_code == 202
    log = csp_db.query(FrontendLogDB).one()
    assert log.environment is None
    assert log.release is None
    stored = json.loads(log.payload_json)
    assert "environment" not in stored
    assert "release" not in stored


def test_reporting_api_batch_has_independent_trace_ids_and_single_commit(
    client,
    csp_db,
    monkeypatch,
):
    commit_calls = 0
    original_commit = csp_db.commit
    trusted_release = "89abcdef0123456789abcdef0123456789abcdef"
    monkeypatch.setattr(frontend_logs_router, "CSP_REPORT_ENVIRONMENT", "staging")
    monkeypatch.setattr(frontend_logs_router, "RELEASE_COMMIT", trusted_release)

    def track_commit():
        nonlocal commit_calls
        commit_calls += 1
        return original_commit()

    monkeypatch.setattr(csp_db, "commit", track_commit)
    payload = [
        _reporting_item(documentURL="https://example.com/products/AU?token=one"),
        _reporting_item(documentURL="https://example.com/products/AG?token=two"),
    ]

    response = _post_json(client, payload, REPORTING_CONTENT_TYPE)

    assert response.status_code == 202
    assert response.json() == {"accepted": 2, "sampled": 0, "persist_failed": 0}
    assert commit_calls == 1
    logs = csp_db.query(FrontendLogDB).order_by(FrontendLogDB.id).all()
    assert len(logs) == 2
    assert all(log.environment == "staging" and log.release == trusted_release for log in logs)
    stored = [json.loads(log.payload_json) for log in logs]
    assert {item["document_url"] for item in stored} == {
        "https://example.com/products/AU",
        "https://example.com/products/AG",
    }
    assert len({item["trace_id"] for item in stored}) == 2


def test_persist_helper_remains_compatible_without_trusted_metadata(csp_db):
    trace_id = "0123456789abcdef0123456789abcdef"
    prepared_reports = [
        (
            trace_id,
            {
                "document_url": "https://example.com/products/AU",
                "blocked_url": "inline",
                "effective_directive": "script-src-elem",
                "disposition": "report",
            },
        )
    ]

    error_type = frontend_logs_router._persist_csp_reports(csp_db, prepared_reports)

    assert error_type is None
    log = csp_db.query(FrontendLogDB).one()
    assert log.environment is None
    assert log.release is None
    assert json.loads(log.payload_json)["trace_id"] == trace_id


@pytest.mark.parametrize(
    ("content_type", "payload", "expected_status"),
    [
        ("application/json", _legacy_report(), 415),
        (LEGACY_CONTENT_TYPE, {"not-a-csp-report": {}}, 422),
        (
            REPORTING_CONTENT_TYPE,
            [{"type": "deprecation", "body": _reporting_item()["body"]}],
            422,
        ),
        (REPORTING_CONTENT_TYPE, [], 422),
        (REPORTING_CONTENT_TYPE, [_reporting_item() for _ in range(21)], 422),
    ],
)
def test_invalid_content_or_structure_is_rejected_safely(
    client,
    csp_db,
    content_type,
    payload,
    expected_status,
):
    rejected_before = _metric_value("rejected")

    response = _post_json(client, payload, content_type)

    assert response.status_code == expected_status
    assert set(response.json()) == {"code", "errors", "message", "timestamp"}
    assert "example.com" not in response.text
    assert _metric_value("rejected") == rejected_before + 1
    assert csp_db.query(FrontendLogDB).count() == 0


def test_oversized_report_is_rejected_before_json_parsing(client, csp_db):
    rejected_before = _metric_value("rejected")
    body = b'{"csp-report":{"document-uri":"' + (b"x" * (9 * 1024)) + b'"}}'

    response = client.post(
        "/api/log/csp-report",
        content=body,
        headers={"Content-Type": LEGACY_CONTENT_TYPE},
    )

    assert response.status_code == 413
    assert response.json()["message"] == "CSP report body exceeds 8 KiB"
    assert _metric_value("rejected") == rejected_before + 1
    assert csp_db.query(FrontendLogDB).count() == 0


def test_malformed_json_returns_fixed_safe_error(client, csp_db):
    response = client.post(
        "/api/log/csp-report",
        content=b'{"csp-report":{"document-uri":"secret-value"',
        headers={"Content-Type": LEGACY_CONTENT_TYPE},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Invalid CSP report JSON"
    assert "secret-value" not in response.text
    assert csp_db.query(FrontendLogDB).count() == 0


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_json_constants_are_rejected_before_validation(
    client,
    csp_db,
    constant,
):
    body = (
        b'{"csp-report":{"document-uri":"https://example.com/products/AU",'
        b'"effective-directive":"script-src","unknown":' + constant.encode("ascii") + b"}}"
    )

    response = client.post(
        "/api/log/csp-report",
        content=body,
        headers={"Content-Type": LEGACY_CONTENT_TYPE},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Invalid CSP report JSON"
    assert constant not in response.text
    assert csp_db.query(FrontendLogDB).count() == 0


@pytest.mark.parametrize("document_field", ["document-uri", "documentURL", "document_url"])
@pytest.mark.parametrize("document_value", ["inline", "data:", "/relative", "https:///missing-host"])
def test_document_url_aliases_require_absolute_http_url_with_hostname(
    client,
    csp_db,
    document_field,
    document_value,
):
    payload = _legacy_report()
    report = payload["csp-report"]
    report.pop("document-uri")
    report[document_field] = document_value

    response = _post_json(client, payload, LEGACY_CONTENT_TYPE)

    assert response.status_code == 422
    assert response.json()["message"] == "Invalid CSP report URL"
    assert document_value not in response.text
    assert csp_db.query(FrontendLogDB).count() == 0


def test_optional_url_fields_apply_field_specific_source_token_policy(client, csp_db):
    payload = _legacy_report(
        **{
            "blocked-uri": "data:",
            "source-file": "inline",
            "referrer": "data:",
        }
    )

    response = _post_json(client, payload, LEGACY_CONTENT_TYPE)

    assert response.status_code == 202
    stored = json.loads(csp_db.query(FrontendLogDB).one().payload_json)
    assert stored["blocked_url"] == "data"
    assert "source_file" not in stored
    assert "referrer" not in stored


@pytest.mark.parametrize(
    "blocked_url",
    [
        "chrome-extension://abcdefghijklmnopabcdefghijklmnop/scripts/injected.js?token=secret#private",
        "moz-extension://01234567-89ab-cdef-0123-456789abcdef/content/main.js?token=secret#private",
    ],
)
def test_browser_extension_blocked_url_is_reduced_to_fixed_category(
    client,
    csp_db,
    blocked_url,
):
    payload = _legacy_report(**{"blocked-uri": blocked_url})

    response = _post_json(client, payload, LEGACY_CONTENT_TYPE)

    assert response.status_code == 202
    stored_json = csp_db.query(FrontendLogDB).one().payload_json
    assert json.loads(stored_json)["blocked_url"] == "browser-extension"
    assert "chrome-extension" not in stored_json
    assert "moz-extension" not in stored_json
    assert "injected.js" not in stored_json
    assert "content/main.js" not in stored_json
    assert "secret" not in stored_json


def test_sanitized_url_path_is_bounded(client, csp_db):
    payload = _legacy_report(
        **{
            "document-uri": f"https://example.com/{'x' * 1000}?token=secret#fragment",
        }
    )

    response = _post_json(client, payload, LEGACY_CONTENT_TYPE)

    assert response.status_code == 202
    log = csp_db.query(FrontendLogDB).one()
    assert log.url == f"https://example.com/{'x' * 299}"
    assert len(log.url) <= 500
    assert "secret" not in log.payload_json


def test_invalid_url_and_directive_boundaries_are_rejected(client, csp_db):
    payload = _legacy_report(
        **{
            "document-uri": "javascript:alert(1)",
            "effective-directive": "script-src;\nset-cookie",
            "line-number": 10_000_001,
        }
    )

    response = _post_json(client, payload, LEGACY_CONTENT_TYPE)

    assert response.status_code == 422
    assert response.json()["message"] == "Invalid CSP report structure"
    assert "javascript" not in response.text
    assert csp_db.query(FrontendLogDB).count() == 0


def test_zero_sample_rate_drops_report_without_persistence(
    client,
    csp_db,
    monkeypatch,
):
    sampled_before = _metric_value("sampled")
    monkeypatch.setattr(frontend_logs_router, "CSP_REPORT_SAMPLE_RATE", 0.0)

    response = _post_json(client, _legacy_report(), LEGACY_CONTENT_TYPE)

    assert response.status_code == 202
    assert response.json() == {"accepted": 0, "sampled": 1, "persist_failed": 0}
    assert _metric_value("sampled") == sampled_before + 1
    assert csp_db.query(FrontendLogDB).count() == 0


def test_sampling_is_deterministic_and_injectable():
    report = {
        "document_url": "https://example.com/products/AU",
        "effective_directive": "script-src",
        "disposition": "report",
    }

    first = frontend_logs_router._should_sample_csp_report(report, sample_rate=0.5)
    second = frontend_logs_router._should_sample_csp_report(report, sample_rate=0.5)

    assert first is second
    assert frontend_logs_router._should_sample_csp_report(report, sample_rate=0) is False
    assert frontend_logs_router._should_sample_csp_report(report, sample_rate=1) is True


@pytest.mark.parametrize("raw_value", ["-0.1", "1.1", "NaN", "Infinity", "not-a-number"])
def test_sample_rate_configuration_rejects_invalid_values(raw_value):
    with pytest.raises(ValueError, match="CSP_REPORT_SAMPLE_RATE"):
        _parse_unit_interval(raw_value, name="CSP_REPORT_SAMPLE_RATE")


def test_dedicated_ip_rate_limit_returns_safe_summary(
    client,
    csp_db,
    monkeypatch,
):
    rate_limited_before = _metric_value("rate_limited")
    observed = {}

    def deny(client_ip, action, *, window_seconds, max_requests):
        observed.update(
            client_ip=client_ip,
            action=action,
            window_seconds=window_seconds,
            max_requests=max_requests,
        )
        return False

    monkeypatch.setattr(frontend_logs_router, "check_rate_limit", deny)

    response = _post_json(client, _legacy_report(), LEGACY_CONTENT_TYPE)

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
    assert response.json()["code"] == "RATE_LIMITED"
    assert response.json()["message"] == "CSP report rate limit exceeded"
    assert observed["action"] == "report:csp"
    assert observed["window_seconds"] == 60
    assert observed["max_requests"] == 60
    assert _metric_value("rate_limited") == rate_limited_before + 1
    assert csp_db.query(FrontendLogDB).count() == 0


def test_sync_rate_limit_and_persistence_cross_threadpool_boundary(
    client,
    csp_db,
    monkeypatch,
):
    calls = []
    original_run_in_threadpool = frontend_logs_router.run_in_threadpool

    async def track_threadpool_call(function, *args, **kwargs):
        calls.append(function)
        return await original_run_in_threadpool(function, *args, **kwargs)

    monkeypatch.setattr(frontend_logs_router, "run_in_threadpool", track_threadpool_call)

    response = _post_json(client, _legacy_report(), LEGACY_CONTENT_TYPE)

    assert response.status_code == 202
    assert calls == [
        frontend_logs_router.check_rate_limit,
        frontend_logs_router._persist_csp_reports,
    ]
    assert csp_db.query(FrontendLogDB).count() == 1


def test_persistence_failure_rolls_back_and_logs_only_safe_diagnostics(
    client,
    csp_db,
    monkeypatch,
    caplog,
):
    persist_failed_before = _metric_value("persist_failed")
    commit_calls = 0
    rollback_calls = 0
    original_commit = csp_db.commit
    original_rollback = csp_db.rollback

    def fail_commit():
        nonlocal commit_calls
        commit_calls += 1
        raise RuntimeError("database failure contains secret-value")

    def track_rollback():
        nonlocal rollback_calls
        rollback_calls += 1
        return original_rollback()

    monkeypatch.setattr(csp_db, "commit", fail_commit)
    monkeypatch.setattr(csp_db, "rollback", track_rollback)
    caplog.set_level(logging.WARNING, logger=frontend_logs_router.__name__)
    payload = [
        _reporting_item(documentURL="https://example.com/products/AU?token=secret-value"),
        _reporting_item(documentURL="https://example.com/products/AG?token=secret-value"),
    ]

    response = _post_json(client, payload, REPORTING_CONTENT_TYPE)
    monkeypatch.setattr(csp_db, "commit", original_commit)
    monkeypatch.setattr(csp_db, "rollback", original_rollback)

    assert response.status_code == 202
    assert response.json() == {"accepted": 0, "sampled": 0, "persist_failed": 2}
    assert commit_calls == 1
    assert rollback_calls == 1
    assert _metric_value("persist_failed") == persist_failed_before + 2
    assert csp_db.query(FrontendLogDB).count() == 0
    records = [record for record in caplog.records if record.getMessage() == "csp_report_persist_failed"]
    assert len(records) == 2
    assert all(re.fullmatch(r"[0-9a-f]{32}", record.trace_id) for record in records)
    assert len({record.trace_id for record in records}) == 2
    assert all(record.error_type == "RuntimeError" for record in records)
    assert all(record.report_count == 2 for record in records)
    assert "secret-value" not in caplog.text


def test_csp_metric_has_only_low_cardinality_outcome_label():
    assert tuple(csp_reports_total._labelnames) == ("outcome",)
