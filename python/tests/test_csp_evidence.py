"""R10 CSP evidence validation, classification, and readiness tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from itertools import product
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

import services.csp_evidence as csp_evidence
from services.csp_evidence import (
    AggregateKey,
    BlockedSourceCategory,
    CatalogDecision,
    CspEvidenceCheckCode,
    CspEvidenceCheckStatus,
    CspEvidenceInputCode,
    CspEvidenceProblemCode,
    CspEvidenceStatus,
    CspEvidenceValidationError,
    DirectiveCategory,
    EvidenceEnvironment,
    EvidenceSource,
    RetestStatus,
    RouteCategory,
    WorkflowName,
    WorkflowStatus,
    classify_blocked_source,
    classify_directive,
    classify_route,
    load_csp_evidence_context,
    load_csp_violation_catalog,
    run_csp_evidence,
    validate_csp_evidence_context,
    validate_csp_violation_catalog,
)

RELEASE = "0123456789abcdef0123456789abcdef01234567"
REPORT_TRACE_ID = "f" * 32
RECORD_TRACE_ID = "a" * 32
NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
WINDOW_START = datetime(2026, 7, 2, 12, 0, tzinfo=UTC)
WINDOW_END = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
EXPECTED_ORIGIN = "https://app.example.com"
TRUSTED_ORIGIN = "https://static.example.com"

WORKFLOW_NAMES = (
    "login",
    "refresh_recovery",
    "concurrent_401_singleflight",
    "logout",
    "sse_initial_connect",
    "sse_reconnect",
    "products",
    "product_detail",
    "workspace",
    "strategies",
    "agents",
    "bearer_write",
    "cookie_only_write_rejected",
    "csp_reporting_canary",
)

ROUTE_CASES = (
    ("/", RouteCategory.HOME),
    ("/products", RouteCategory.PRODUCTS),
    ("/products/AU", RouteCategory.PRODUCT_DETAIL),
    ("/workspace", RouteCategory.WORKSPACE),
    ("/my-comments", RouteCategory.MY_COMMENTS),
    ("/agents", RouteCategory.AGENTS),
    ("/agents/detail", RouteCategory.AGENT_DETAIL),
    ("/chat", RouteCategory.CHAT),
    ("/strategies", RouteCategory.STRATEGIES),
    ("/strategies/evolution", RouteCategory.STRATEGY_EVOLUTION),
    ("/alerts", RouteCategory.ALERTS),
    ("/news", RouteCategory.NEWS),
    ("/opinions", RouteCategory.OPINIONS),
    ("/portfolio", RouteCategory.PORTFOLIO),
    ("/metrics", RouteCategory.METRICS),
    ("/settings", RouteCategory.SETTINGS),
    ("/not-a-fixed-route", RouteCategory.UNKNOWN),
)

DIRECTIVE_CASES = (
    ("script-src", DirectiveCategory.SCRIPT_SRC),
    ("script-src-elem", DirectiveCategory.SCRIPT_SRC_ELEM),
    ("script-src-attr", DirectiveCategory.SCRIPT_SRC_ATTR),
    ("style-src", DirectiveCategory.STYLE_SRC),
    ("style-src-elem", DirectiveCategory.STYLE_SRC_ELEM),
    ("style-src-attr", DirectiveCategory.STYLE_SRC_ATTR),
    ("connect-src", DirectiveCategory.CONNECT_SRC),
    ("img-src", DirectiveCategory.IMG_SRC),
    ("font-src", DirectiveCategory.FONT_SRC),
    ("frame-src", DirectiveCategory.FRAME_SRC),
    ("worker-src", DirectiveCategory.WORKER_SRC),
    ("default-src", DirectiveCategory.DEFAULT_SRC),
    ("base-uri", DirectiveCategory.BASE_URI),
    ("form-action", DirectiveCategory.FORM_ACTION),
    ("object-src", DirectiveCategory.OBJECT_SRC),
    ("frame-ancestors", DirectiveCategory.FRAME_ANCESTORS),
    ("manifest-src", DirectiveCategory.MANIFEST_SRC),
    ("media-src", DirectiveCategory.MEDIA_SRC),
    ("child-src", DirectiveCategory.CHILD_SRC),
    ("report-uri", DirectiveCategory.UNKNOWN),
)

SOURCE_CASES = (
    ("inline", BlockedSourceCategory.INLINE),
    ("eval", BlockedSourceCategory.EVAL),
    ("data", BlockedSourceCategory.DATA),
    ("blob", BlockedSourceCategory.BLOB),
    ("browser-extension", BlockedSourceCategory.BROWSER_EXTENSION),
    ("https://app.example.com/assets/app.js", BlockedSourceCategory.SAME_ORIGIN),
    ("https://static.example.com/assets/vendor.js", BlockedSourceCategory.TRUSTED_SOURCE),
    ("https://outside.example.net/library.js", BlockedSourceCategory.EXTERNAL_UNTRUSTED),
    (None, BlockedSourceCategory.UNKNOWN),
)


@pytest.fixture
def evidence_engine() -> Engine:
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    yield engine
    engine.dispose()


def _context_document(
    *,
    accepted: int = 1,
    received: int | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    document: dict[str, Any] = {
        "schema_version": 1,
        "evidence_source": "target_environment",
        "environment": "production",
        "release": RELEASE,
        "window_start": "2026-07-02T12:00:00Z",
        "window_end": "2026-08-02T12:00:00Z",
        "sample_rate": 1.0,
        "complete_business_cycle": True,
        "workflows": dict.fromkeys(WORKFLOW_NAMES, "passed"),
        "metrics": {
            "business_http_requests": 100,
            "csp_outcomes": {
                "received": max(accepted, 1) if received is None else received,
                "accepted": accepted,
                "sampled": 0,
                "rejected": 0,
                "rate_limited": 0,
                "persist_failed": 0,
            },
        },
        "expected_document_origins": [EXPECTED_ORIGIN],
        "trusted_source_origins": [TRUSTED_ORIGIN],
    }
    document.update(overrides)
    return document


def _context(*, accepted: int = 1, received: int | None = None, **overrides: Any):
    return validate_csp_evidence_context(_context_document(accepted=accepted, received=received, **overrides))


def _catalog_entry(
    *,
    catalog_id: str = "known-inline-script",
    route: str = "product_detail",
    directive: str = "script_src_elem",
    source: str = "inline",
    owner_role: str = "security-team",
    decision: str = "remediate_before_s2",
    retest: str = "passed",
    **extra: Any,
) -> dict[str, Any]:
    entry = {
        "catalog_id": catalog_id,
        "route_category": route,
        "directive_category": directive,
        "blocked_source_category": source,
        "owner_role": owner_role,
        "decision": decision,
        "retest_status": retest,
    }
    entry.update(extra)
    return entry


def _catalog(*entries: dict[str, Any]):
    return validate_csp_violation_catalog(
        {
            "schema_version": 1,
            "entries": list(entries),
        }
    )


def _payload(
    *,
    trace_id: str = RECORD_TRACE_ID,
    document_url: str = f"{EXPECTED_ORIGIN}/products/AU",
    blocked_url: str | None = "inline",
    directive: str = "script-src-elem",
    disposition: str = "report",
    **extra: Any,
) -> str:
    payload: dict[str, Any] = {
        "trace_id": trace_id,
        "document_url": document_url,
        "effective_directive": directive,
        "disposition": disposition,
    }
    if blocked_url is not None:
        payload["blocked_url"] = blocked_url
    payload.update(extra)
    return json.dumps(payload, separators=(",", ":"))


def _row(
    row_id: int,
    payload_json: str | None = None,
    *,
    environment: str | None = "production",
    release: str | None = RELEASE,
    created_at: datetime = NOW,
) -> dict[str, Any]:
    return {
        "id": row_id,
        "payload_json": _payload() if payload_json is None else payload_json,
        "environment": environment,
        "release": release,
        "created_at": created_at,
    }


def _install_rows(monkeypatch: pytest.MonkeyPatch, rows: list[dict[str, Any]]) -> None:
    ordered = sorted(rows, key=lambda row: row["id"])

    def query_page(
        connection: Any,
        context: Any,
        last_id: int,
        *,
        page_limit: int = csp_evidence.CSP_EVIDENCE_PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        del connection, context
        return [row for row in ordered if row["id"] > last_id][:page_limit]

    monkeypatch.setattr(csp_evidence, "_query_page", query_page)


def _run_rows(
    monkeypatch: pytest.MonkeyPatch,
    engine: Engine,
    rows: list[dict[str, Any]],
    *,
    context: Any | None = None,
    catalog: Any | None = None,
    clock: Any = None,
):
    _install_rows(monkeypatch, rows)
    effective_context = context or _context(accepted=len(rows))
    effective_catalog = catalog or _catalog()
    arguments = {
        "trace_id": REPORT_TRACE_ID,
        "now": NOW,
    }
    if clock is not None:
        arguments["clock"] = clock
    return run_csp_evidence(
        engine,
        effective_context,
        effective_catalog,
        **arguments,
    )


def _problem_counts(report: Any) -> dict[CspEvidenceProblemCode, int]:
    return {problem.code: problem.count for problem in report.problems}


def _assert_input_error(
    code: CspEvidenceInputCode,
    function: Any,
    value: Any,
) -> None:
    with pytest.raises(CspEvidenceValidationError) as caught:
        function(value)
    assert caught.value.code is code
    assert str(caught.value) == code.value


def _unique_catalog_entries(count: int) -> list[dict[str, Any]]:
    classifications = product(RouteCategory, DirectiveCategory, BlockedSourceCategory)
    return [
        _catalog_entry(
            catalog_id=f"catalog-{index:03d}",
            route=route.value,
            directive=directive.value,
            source=source.value,
        )
        for index, (route, directive, source) in zip(range(count), classifications, strict=False)
    ]


@pytest.mark.parametrize(
    ("loader", "document", "filename"),
    [
        (load_csp_evidence_context, _context_document(), "context.json"),
        (
            load_csp_violation_catalog,
            {"schema_version": 1, "entries": []},
            "catalog.json",
        ),
    ],
    ids=("context", "catalog"),
)
def test_input_files_accept_exactly_64_kib(
    loader: Any,
    document: dict[str, Any],
    filename: str,
    tmp_path: Path,
):
    serialized = json.dumps(document, separators=(",", ":")).encode("utf-8")
    payload = serialized + (b" " * (csp_evidence.CSP_EVIDENCE_INPUT_MAX_BYTES - len(serialized)))
    path = tmp_path / filename
    path.write_bytes(payload)

    loaded = loader(path)

    assert loaded.schema_version == 1
    assert path.stat().st_size == 64 * 1024


@pytest.mark.parametrize(
    ("loader", "document", "expected_code"),
    [
        (
            load_csp_evidence_context,
            _context_document(),
            CspEvidenceInputCode.CONTEXT_TOO_LARGE,
        ),
        (
            load_csp_violation_catalog,
            {"schema_version": 1, "entries": []},
            CspEvidenceInputCode.CATALOG_TOO_LARGE,
        ),
    ],
    ids=("context", "catalog"),
)
def test_input_files_reject_64_kib_plus_one_without_echoing_content(
    loader: Any,
    document: dict[str, Any],
    expected_code: CspEvidenceInputCode,
    tmp_path: Path,
):
    serialized = json.dumps(document, separators=(",", ":")).encode("utf-8")
    secret = b"must-not-be-echoed"
    padding_length = csp_evidence.CSP_EVIDENCE_INPUT_MAX_BYTES + 1 - len(serialized) - len(secret)
    path = tmp_path / "oversized-secret.json"
    path.write_bytes(serialized + (b" " * padding_length) + secret)

    with pytest.raises(CspEvidenceValidationError) as caught:
        loader(path)

    assert caught.value.code is expected_code
    assert secret.decode() not in str(caught.value)


@pytest.mark.parametrize(
    ("loader", "expected_code"),
    [
        (load_csp_evidence_context, CspEvidenceInputCode.CONTEXT_INVALID_UTF8),
        (load_csp_violation_catalog, CspEvidenceInputCode.CATALOG_INVALID_UTF8),
    ],
    ids=("context", "catalog"),
)
def test_input_files_require_utf8(
    loader: Any,
    expected_code: CspEvidenceInputCode,
    tmp_path: Path,
):
    path = tmp_path / "invalid-utf8.json"
    path.write_bytes(b'{"secret":"\xff"}')

    with pytest.raises(CspEvidenceValidationError) as caught:
        loader(path)

    assert caught.value.code is expected_code
    assert "secret" not in str(caught.value)


@pytest.mark.parametrize("value", [None, [], "context"])
def test_context_requires_an_exact_versioned_object(value: object):
    _assert_input_error(
        CspEvidenceInputCode.CONTEXT_INVALID_STRUCTURE,
        validate_csp_evidence_context,
        value,
    )


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ({"schema_version": 2}, CspEvidenceInputCode.CONTEXT_INVALID_SCHEMA_VERSION),
        ({"unexpected": "secret"}, CspEvidenceInputCode.CONTEXT_INVALID_STRUCTURE),
    ],
)
def test_context_rejects_wrong_schema_and_extra_keys(
    mutation: dict[str, Any],
    expected_code: CspEvidenceInputCode,
):
    document = _context_document()
    document.update(mutation)

    _assert_input_error(expected_code, validate_csp_evidence_context, document)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_required",
        "missing_workflows",
        "ambiguous_workflows",
        "missing_metrics",
        "ambiguous_metrics",
    ],
)
def test_context_rejects_missing_or_ambiguous_structural_sections(mutation: str):
    document = _context_document()
    if mutation == "missing_required":
        document.pop("release")
    elif mutation == "missing_workflows":
        document.pop("workflows")
    elif mutation == "ambiguous_workflows":
        document["core_workflows"] = document["workflows"]
    elif mutation == "missing_metrics":
        document.pop("metrics")
    else:
        document["window_metrics"] = document["metrics"]

    _assert_input_error(
        CspEvidenceInputCode.CONTEXT_INVALID_STRUCTURE,
        validate_csp_evidence_context,
        document,
    )


@pytest.mark.parametrize(
    ("field", "value", "expected_code"),
    [
        ("evidence_source", "browser", CspEvidenceInputCode.CONTEXT_INVALID_ENUM),
        ("environment", "Production", CspEvidenceInputCode.CONTEXT_INVALID_ENUM),
        ("release", "0" * 39, CspEvidenceInputCode.CONTEXT_INVALID_RELEASE),
        ("release", "A" * 40, CspEvidenceInputCode.CONTEXT_INVALID_RELEASE),
        ("release", ("0" * 39) + "g", CspEvidenceInputCode.CONTEXT_INVALID_RELEASE),
        ("complete_business_cycle", 1, CspEvidenceInputCode.CONTEXT_INVALID_STRUCTURE),
    ],
)
def test_context_rejects_uncontrolled_enums_release_and_boolean(
    field: str,
    value: object,
    expected_code: CspEvidenceInputCode,
):
    document = _context_document()
    document[field] = value

    _assert_input_error(expected_code, validate_csp_evidence_context, document)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2026-07-02T12:00:00", "2026-08-02T12:00:00Z"),
        ("2026-07-02T20:00:00+08:00", "2026-08-02T12:00:00Z"),
        ("2026-07-02T12:00:00Z", "2026-08-02T20:00:00+08:00"),
        ("2026-08-02T12:00:00Z", "2026-08-02T12:00:00Z"),
        ("2026-08-03T12:00:00Z", "2026-08-02T12:00:00Z"),
        ("2026-07-02T11:59:59.999999Z", "2026-08-02T12:00:00Z"),
    ],
)
def test_context_requires_ordered_utc_window_at_most_31_days(start: str, end: str):
    document = _context_document(window_start=start, window_end=end)

    _assert_input_error(
        CspEvidenceInputCode.CONTEXT_INVALID_WINDOW,
        validate_csp_evidence_context,
        document,
    )


def test_context_accepts_exactly_31_days_and_normalizes_zulu_time():
    context = _context()

    assert context.window_end - context.window_start == timedelta(days=31)
    assert context.window_start.tzinfo is UTC
    assert context.window_end.tzinfo is UTC


@pytest.mark.parametrize(
    "sample_rate",
    [float("nan"), float("inf"), float("-inf"), -0.0001, 1.0001, True, "1"],
)
def test_context_sample_rate_must_be_a_finite_unit_interval(sample_rate: object):
    document = _context_document(sample_rate=sample_rate)

    _assert_input_error(
        CspEvidenceInputCode.CONTEXT_INVALID_SAMPLE_RATE,
        validate_csp_evidence_context,
        document,
    )


def test_context_requires_the_exact_14_workflow_matrix_in_enum_order():
    context = _context()

    assert len(context.workflows) == 14
    assert tuple(name.value for name in WorkflowName) == WORKFLOW_NAMES
    assert tuple(result.name for result in context.workflows) == tuple(WorkflowName)
    assert {result.status for result in context.workflows} == {WorkflowStatus.PASSED}


@pytest.mark.parametrize(
    ("operation", "value"),
    [
        ("remove", "login"),
        ("add", "future_workflow"),
        ("replace", ("login", "skipped")),
        ("replace", ("login", True)),
        ("replace_object", []),
    ],
)
def test_context_rejects_missing_extra_or_invalid_workflow_status(
    operation: str,
    value: object,
):
    document = _context_document()
    workflows = document["workflows"]
    if operation == "remove":
        workflows.pop(value)
    elif operation == "add":
        workflows[value] = "passed"
    elif operation == "replace":
        name, status = value
        workflows[name] = status
    else:
        document["workflows"] = value

    _assert_input_error(
        CspEvidenceInputCode.CONTEXT_INVALID_WORKFLOWS,
        validate_csp_evidence_context,
        document,
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("business_http_requests",), -1),
        (("business_http_requests",), True),
        (("csp_outcomes", "accepted"), 1.5),
        (("csp_outcomes", "sampled"), True),
        (("csp_outcomes", "persist_failed"), -1),
    ],
)
def test_context_metrics_require_non_negative_integers(
    path: tuple[str, ...],
    value: object,
):
    document = _context_document()
    metrics = document["metrics"]
    if len(path) == 1:
        metrics[path[0]] = value
    else:
        metrics[path[0]][path[1]] = value

    _assert_input_error(
        CspEvidenceInputCode.CONTEXT_INVALID_METRICS,
        validate_csp_evidence_context,
        document,
    )


@pytest.mark.parametrize("mutation", ["missing", "extra", "not_object"])
def test_context_metrics_require_the_exact_counter_schema(mutation: str):
    document = _context_document()
    if mutation == "missing":
        document["metrics"]["csp_outcomes"].pop("rejected")
    elif mutation == "extra":
        document["metrics"]["csp_outcomes"]["unknown"] = 1
    else:
        document["metrics"] = []

    _assert_input_error(
        CspEvidenceInputCode.CONTEXT_INVALID_METRICS,
        validate_csp_evidence_context,
        document,
    )


def test_context_accepts_and_canonicalizes_at_most_20_https_production_origins():
    origins = [f"https://service-{index}.example.com:443/" for index in range(20)]
    document = _context_document(
        expected_document_origins=origins,
        trusted_source_origins=list(reversed(origins)),
    )

    context = validate_csp_evidence_context(document)

    assert len(context.expected_document_origins) == 20
    assert context.expected_document_origins[0] == "https://service-0.example.com"
    assert context.trusted_source_origins[-1] == "https://service-0.example.com"


@pytest.mark.parametrize(
    "origin",
    [
        "http://app.example.com",
        "https://user:password@app.example.com",
        "https://app.example.com/private",
        "https://app.example.com?token=secret",
        "https://app.example.com#fragment",
        "https://app.example.com:bad-port",
        "ftp://app.example.com",
        "https://",
    ],
)
def test_production_context_rejects_non_https_or_non_origin_values(origin: str):
    document = _context_document(expected_document_origins=[origin])

    _assert_input_error(
        CspEvidenceInputCode.CONTEXT_INVALID_ORIGINS,
        validate_csp_evidence_context,
        document,
    )


def test_context_rejects_more_than_20_or_duplicate_origins():
    too_many = _context_document(
        expected_document_origins=[f"https://service-{index}.example.com" for index in range(21)]
    )
    duplicates = _context_document(
        expected_document_origins=["https://app.example.com", "https://APP.EXAMPLE.COM:443/"]
    )

    _assert_input_error(
        CspEvidenceInputCode.CONTEXT_INVALID_ORIGINS,
        validate_csp_evidence_context,
        too_many,
    )
    _assert_input_error(
        CspEvidenceInputCode.CONTEXT_INVALID_ORIGINS,
        validate_csp_evidence_context,
        duplicates,
    )


def test_non_production_context_can_use_a_canonical_http_origin():
    context = _context(
        environment="development",
        expected_document_origins=["HTTP://LOCALHOST:80/"],
        trusted_source_origins=[],
    )

    assert context.environment is EvidenceEnvironment.DEVELOPMENT
    assert context.expected_document_origins == ("http://localhost",)


@pytest.mark.parametrize("value", [None, [], "catalog"])
def test_catalog_requires_an_exact_versioned_object(value: object):
    _assert_input_error(
        CspEvidenceInputCode.CATALOG_INVALID_STRUCTURE,
        validate_csp_violation_catalog,
        value,
    )


@pytest.mark.parametrize(
    ("document", "expected_code"),
    [
        (
            {"schema_version": 2, "entries": []},
            CspEvidenceInputCode.CATALOG_INVALID_SCHEMA_VERSION,
        ),
        (
            {"schema_version": 1, "entries": [], "evidence": "secret"},
            CspEvidenceInputCode.CATALOG_INVALID_STRUCTURE,
        ),
        (
            {"schema_version": 1, "entries": "not-a-list"},
            CspEvidenceInputCode.CATALOG_INVALID_STRUCTURE,
        ),
    ],
)
def test_catalog_rejects_wrong_schema_extra_keys_and_non_list_entries(
    document: dict[str, Any],
    expected_code: CspEvidenceInputCode,
):
    _assert_input_error(expected_code, validate_csp_violation_catalog, document)


def test_catalog_accepts_500_unique_entries_and_rejects_501():
    entries = _unique_catalog_entries(501)

    catalog = _catalog(*entries[:500])

    assert len(catalog.entries) == 500
    _assert_input_error(
        CspEvidenceInputCode.CATALOG_TOO_MANY_ENTRIES,
        validate_csp_violation_catalog,
        {"schema_version": 1, "entries": entries},
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("catalog_id", ""),
        ("catalog_id", "a" * 65),
        ("catalog_id", "contains space"),
        ("catalog_id", "非ascii"),
        ("catalog_id", "-leading"),
        ("owner_role", ""),
        ("owner_role", "security/team"),
        ("owner_role", "a" * 65),
    ],
)
def test_catalog_ids_and_owner_roles_are_bounded_ascii_slugs(field: str, value: str):
    entry = _catalog_entry()
    entry[field] = value

    _assert_input_error(
        CspEvidenceInputCode.CATALOG_INVALID_ENTRY,
        validate_csp_violation_catalog,
        {"schema_version": 1, "entries": [entry]},
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("route_category", "private_page"),
        ("directive_category", "report_uri"),
        ("blocked_source_category", "javascript"),
        ("decision", "approved"),
        ("retest_status", "skipped"),
    ],
)
def test_catalog_rejects_values_outside_fixed_enums(field: str, value: str):
    entry = _catalog_entry()
    entry[field] = value

    _assert_input_error(
        CspEvidenceInputCode.CATALOG_INVALID_ENTRY,
        validate_csp_violation_catalog,
        {"schema_version": 1, "entries": [entry]},
    )


def test_catalog_rejects_duplicate_ids_and_classifications_independently():
    first = _catalog_entry()
    duplicate_id = _catalog_entry(
        catalog_id=first["catalog_id"],
        route="home",
        directive="style_src",
        source="data",
    )
    duplicate_classification = _catalog_entry(catalog_id="different-id")

    _assert_input_error(
        CspEvidenceInputCode.CATALOG_DUPLICATE_ID,
        validate_csp_violation_catalog,
        {"schema_version": 1, "entries": [first, duplicate_id]},
    )
    _assert_input_error(
        CspEvidenceInputCode.CATALOG_DUPLICATE_CLASSIFICATION,
        validate_csp_violation_catalog,
        {"schema_version": 1, "entries": [first, duplicate_classification]},
    )


@pytest.mark.parametrize(
    "decision",
    [
        "migrate_nonce_in_s2",
        "migrate_hash_in_s2",
        "remove_source_in_s2",
    ],
)
def test_catalog_allows_not_applicable_retest_only_for_deferred_s2_decisions(decision: str):
    catalog = _catalog(_catalog_entry(decision=decision, retest="not_applicable"))

    assert catalog.entries[0].decision is CatalogDecision(decision)
    assert catalog.entries[0].retest_status is RetestStatus.NOT_APPLICABLE


@pytest.mark.parametrize("decision", ["remediate_before_s2", "not_applicable"])
def test_catalog_rejects_invalid_not_applicable_retest_combinations(decision: str):
    entry = _catalog_entry(decision=decision, retest="not_applicable")

    _assert_input_error(
        CspEvidenceInputCode.CATALOG_INVALID_RETEST_COMBINATION,
        validate_csp_violation_catalog,
        {"schema_version": 1, "entries": [entry]},
    )


@pytest.mark.parametrize(
    "sensitive_key",
    [
        "url",
        "script_sample",
        "dom",
        "user_agent",
        "credential",
        "record_trace",
        "payload",
        "file_path",
        "free_text_evidence",
    ],
)
def test_catalog_entries_reject_every_extra_sensitive_or_free_text_field(sensitive_key: str):
    entry = _catalog_entry(**{sensitive_key: "must-not-be-retained"})

    with pytest.raises(CspEvidenceValidationError) as caught:
        validate_csp_violation_catalog({"schema_version": 1, "entries": [entry]})

    assert caught.value.code is CspEvidenceInputCode.CATALOG_INVALID_ENTRY
    assert "must-not-be-retained" not in str(caught.value)


@pytest.mark.parametrize(("path", "expected"), ROUTE_CASES)
def test_all_17_fixed_route_categories(path: str, expected: RouteCategory):
    assert classify_route(path) is expected


def test_route_matrix_is_complete_and_specific_routes_win():
    assert {expected for _, expected in ROUTE_CASES} == set(RouteCategory)
    assert classify_route("/products/AU/") is RouteCategory.PRODUCT_DETAIL
    assert classify_route("/agents/detail/") is RouteCategory.AGENT_DETAIL
    assert classify_route("/strategies/evolution/") is RouteCategory.STRATEGY_EVOLUTION
    assert classify_route("/agents/detail/private") is RouteCategory.UNKNOWN
    assert classify_route("/strategies/evolution/private") is RouteCategory.UNKNOWN


@pytest.mark.parametrize(("directive", "expected"), DIRECTIVE_CASES)
def test_all_20_fixed_directive_categories(
    directive: str,
    expected: DirectiveCategory,
):
    assert classify_directive(directive) is expected


def test_directive_matrix_is_complete_and_exact():
    assert {expected for _, expected in DIRECTIVE_CASES} == set(DirectiveCategory)
    assert classify_directive("Script-Src") is DirectiveCategory.UNKNOWN
    assert classify_directive(None) is DirectiveCategory.UNKNOWN


@pytest.mark.parametrize(("blocked_url", "expected"), SOURCE_CASES)
def test_all_nine_fixed_blocked_source_categories(
    blocked_url: str | None,
    expected: BlockedSourceCategory,
):
    assert (
        classify_blocked_source(
            blocked_url,
            f"{EXPECTED_ORIGIN}/products/AU",
            [TRUSTED_ORIGIN],
        )
        is expected
    )


def test_blocked_source_matrix_is_complete_and_origin_comparison_is_exact():
    assert {expected for _, expected in SOURCE_CASES} == set(BlockedSourceCategory)
    assert (
        classify_blocked_source(
            "https://app.example.com.evil.test/app.js",
            f"{EXPECTED_ORIGIN}/products/AU",
            [TRUSTED_ORIGIN],
        )
        is BlockedSourceCategory.EXTERNAL_UNTRUSTED
    )


def test_unexpected_document_origin_blocks_without_disclosing_origin(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    unexpected_origin = "https://unexpected-secret.example.net"
    rows = [_row(1, _payload(document_url=f"{unexpected_origin}/products/SECRET"))]

    report = _run_rows(monkeypatch, evidence_engine, rows)

    assert report.status is CspEvidenceStatus.BLOCKED
    assert _problem_counts(report) == {
        CspEvidenceProblemCode.UNEXPECTED_DOCUMENT_ORIGIN: 1,
    }
    assert report.counts.invalid_records == 1
    assert unexpected_origin not in report.to_json()
    assert "SECRET" not in report.to_json()


@pytest.mark.parametrize(
    ("payload_json", "expected_problem", "expected_key", "secret"),
    [
        (
            _payload(document_url=f"{EXPECTED_ORIGIN}/private-route-secret"),
            CspEvidenceProblemCode.UNKNOWN_ROUTE_CATEGORY,
            AggregateKey(
                RouteCategory.UNKNOWN,
                DirectiveCategory.SCRIPT_SRC_ELEM,
                BlockedSourceCategory.INLINE,
            ),
            "private-route-secret",
        ),
        (
            _payload(directive="report-uri"),
            CspEvidenceProblemCode.UNKNOWN_DIRECTIVE_CATEGORY,
            AggregateKey(
                RouteCategory.PRODUCT_DETAIL,
                DirectiveCategory.UNKNOWN,
                BlockedSourceCategory.INLINE,
            ),
            "report-uri",
        ),
        (
            _payload(blocked_url=None),
            CspEvidenceProblemCode.UNKNOWN_BLOCKED_SOURCE_CATEGORY,
            AggregateKey(
                RouteCategory.PRODUCT_DETAIL,
                DirectiveCategory.SCRIPT_SRC_ELEM,
                BlockedSourceCategory.UNKNOWN,
            ),
            RECORD_TRACE_ID,
        ),
    ],
    ids=("route", "directive", "blocked-source"),
)
def test_unknown_classifications_block_through_the_report_state_machine_without_echo(
    payload_json: str,
    expected_problem: CspEvidenceProblemCode,
    expected_key: AggregateKey,
    secret: str,
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    report = _run_rows(
        monkeypatch,
        evidence_engine,
        [_row(1, payload_json)],
        catalog=_catalog(),
    )

    assert report.status is CspEvidenceStatus.BLOCKED
    assert report.aggregates[0].key == expected_key
    assert report.unknown_violations[0].key == expected_key
    assert _problem_counts(report) == {
        expected_problem: 1,
        CspEvidenceProblemCode.UNKNOWN_VIOLATION: 1,
    }
    assert secret not in report.to_json()


def test_complete_production_evidence_is_ready_with_known_catalog_match(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    report = _run_rows(
        monkeypatch,
        evidence_engine,
        [_row(1)],
        catalog=_catalog(_catalog_entry()),
    )

    assert report.status is CspEvidenceStatus.READY_FOR_REVIEW
    assert report.ready_for_review is True
    assert report.problems == ()
    assert report.counts.scanned_records == 1
    assert report.counts.target_records == 1
    assert report.counts.classified_records == 1
    assert report.counts.known_records == 1
    assert report.counts.unknown_records == 0
    assert len(report.known_violations) == 1
    assert report.unknown_violations == ()
    assert all(check.status is CspEvidenceCheckStatus.PASSED for check in report.checks)
    assert [check.code for check in report.checks] == list(CspEvidenceCheckCode)


def test_complete_synthetic_evidence_never_becomes_ready(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    context = _context(accepted=1, evidence_source="synthetic")

    report = _run_rows(
        monkeypatch,
        evidence_engine,
        [_row(1)],
        context=context,
        catalog=_catalog(_catalog_entry()),
    )

    assert context.evidence_source is EvidenceSource.SYNTHETIC
    assert report.status is CspEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert _problem_counts(report) == {CspEvidenceProblemCode.SYNTHETIC_EVIDENCE: 1}


def test_zero_rows_is_insufficient_instead_of_evidence_of_no_violations(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    report = _run_rows(
        monkeypatch,
        evidence_engine,
        [],
        context=_context(accepted=0, received=1),
    )

    assert report.status is CspEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert report.counts.scanned_records == 0
    assert report.counts.target_records == 0
    assert _problem_counts(report) == {CspEvidenceProblemCode.NO_TARGET_RECORDS: 1}


def test_known_and_unknown_violations_are_counted_and_unknown_blocks(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    rows = [
        _row(1),
        _row(
            2,
            _payload(
                document_url=f"{EXPECTED_ORIGIN}/workspace",
                blocked_url="data",
                directive="style-src",
                trace_id="b" * 32,
            ),
        ),
    ]

    report = _run_rows(
        monkeypatch,
        evidence_engine,
        rows,
        catalog=_catalog(_catalog_entry()),
    )

    assert report.status is CspEvidenceStatus.BLOCKED
    assert report.counts.known_records == 1
    assert report.counts.unknown_records == 1
    assert report.counts.known_groups == 1
    assert report.counts.unknown_groups == 1
    assert _problem_counts(report)[CspEvidenceProblemCode.UNKNOWN_VIOLATION] == 1


@pytest.mark.parametrize(
    ("retest", "expected_code"),
    [
        ("pending", CspEvidenceProblemCode.CATALOG_RETEST_PENDING),
        ("failed", CspEvidenceProblemCode.CATALOG_RETEST_FAILED),
    ],
)
def test_pending_or_failed_catalog_retest_blocks_even_when_observation_is_known(
    retest: str,
    expected_code: CspEvidenceProblemCode,
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    report = _run_rows(
        monkeypatch,
        evidence_engine,
        [_row(1)],
        catalog=_catalog(_catalog_entry(retest=retest)),
    )

    assert report.status is CspEvidenceStatus.BLOCKED
    assert report.counts.known_records == 1
    assert _problem_counts(report)[expected_code] == 1


@pytest.mark.parametrize(
    ("overrides", "expected_code", "expected_count"),
    [
        ({"evidence_source": "synthetic"}, CspEvidenceProblemCode.SYNTHETIC_EVIDENCE, 1),
        ({"environment": "staging"}, CspEvidenceProblemCode.NON_PRODUCTION_ENVIRONMENT, 1),
        (
            {"complete_business_cycle": False},
            CspEvidenceProblemCode.INCOMPLETE_BUSINESS_CYCLE,
            1,
        ),
        (
            {
                "workflows": {
                    **dict.fromkeys(WORKFLOW_NAMES, "passed"),
                    "login": "failed",
                    "logout": "not_run",
                }
            },
            CspEvidenceProblemCode.WORKFLOW_NOT_PASSED,
            2,
        ),
        ({"sample_rate": 0}, CspEvidenceProblemCode.ZERO_SAMPLE_RATE, 1),
    ],
)
def test_context_process_gaps_are_insufficient(
    overrides: dict[str, Any],
    expected_code: CspEvidenceProblemCode,
    expected_count: int,
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    context = _context(accepted=1, **overrides)
    rows = [
        _row(
            1,
            environment=context.environment.value,
            release=context.release,
        )
    ]

    report = _run_rows(
        monkeypatch,
        evidence_engine,
        rows,
        context=context,
        catalog=_catalog(_catalog_entry()),
    )

    assert report.status is CspEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert _problem_counts(report)[expected_code] == expected_count


@pytest.mark.parametrize(
    ("missing_field", "expected_count"),
    [
        ("business_http_requests", 1),
        ("received", 1),
        ("both", 2),
    ],
)
def test_missing_window_traffic_metrics_are_insufficient(
    missing_field: str,
    expected_count: int,
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    document = _context_document(accepted=1)
    if missing_field in {"business_http_requests", "both"}:
        document["metrics"]["business_http_requests"] = 0
    if missing_field in {"received", "both"}:
        document["metrics"]["csp_outcomes"]["received"] = 0
    context = validate_csp_evidence_context(document)

    report = _run_rows(
        monkeypatch,
        evidence_engine,
        [_row(1)],
        context=context,
        catalog=_catalog(_catalog_entry()),
    )

    assert report.status is CspEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert _problem_counts(report)[CspEvidenceProblemCode.MISSING_TRAFFIC_METRICS] == expected_count


def test_unscoped_record_is_counted_without_becoming_an_aggregate(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    report = _run_rows(
        monkeypatch,
        evidence_engine,
        [_row(1, environment=None, release=None)],
        catalog=_catalog(_catalog_entry()),
    )

    assert report.status is CspEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert report.counts.scanned_records == 1
    assert report.counts.target_records == 0
    assert report.counts.unscoped_records == 1
    assert report.counts.classified_records == 0
    assert report.aggregates == ()
    assert _problem_counts(report)[CspEvidenceProblemCode.UNSCOPED_RECORDS] == 1


@pytest.mark.parametrize(
    ("environment", "release"),
    [
        ("staging", RELEASE),
        ("production", "f" * 40),
    ],
)
def test_record_scope_mismatch_blocks_and_is_not_aggregated(
    environment: str,
    release: str,
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    report = _run_rows(
        monkeypatch,
        evidence_engine,
        [_row(1, environment=environment, release=release)],
        catalog=_catalog(_catalog_entry()),
    )

    assert report.status is CspEvidenceStatus.BLOCKED
    assert report.counts.scope_mismatch_records == 1
    assert report.counts.target_records == 0
    assert report.counts.classified_records == 0
    assert _problem_counts(report)[CspEvidenceProblemCode.RECORD_SCOPE_MISMATCH] == 1


def test_complete_scan_accepted_count_mismatch_blocks(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    report = _run_rows(
        monkeypatch,
        evidence_engine,
        [_row(1)],
        context=_context(accepted=2, received=2),
        catalog=_catalog(_catalog_entry()),
    )

    assert report.status is CspEvidenceStatus.BLOCKED
    assert _problem_counts(report)[CspEvidenceProblemCode.ACCEPTED_COUNT_MISMATCH] == 1
    metrics_check = next(check for check in report.checks if check.code is CspEvidenceCheckCode.METRICS_CONSISTENT)
    assert metrics_check.status is CspEvidenceCheckStatus.FAILED


def test_persist_failed_metric_blocks_with_exact_failure_count(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    document = _context_document(accepted=1)
    document["metrics"]["csp_outcomes"]["persist_failed"] = 3

    report = _run_rows(
        monkeypatch,
        evidence_engine,
        [_row(1)],
        context=validate_csp_evidence_context(document),
        catalog=_catalog(_catalog_entry()),
    )

    assert report.status is CspEvidenceStatus.BLOCKED
    assert _problem_counts(report)[CspEvidenceProblemCode.PERSIST_FAILED] == 3


@pytest.mark.parametrize(
    ("payload_json", "expected_code", "secret"),
    [
        (
            '{"malformed-secret-marker":',
            CspEvidenceProblemCode.PAYLOAD_MALFORMED_JSON,
            "malformed-secret-marker",
        ),
        (
            '["nonobject-secret-marker"]',
            CspEvidenceProblemCode.PAYLOAD_NOT_OBJECT,
            "nonobject-secret-marker",
        ),
        (
            _payload(note="benign-extra-value"),
            CspEvidenceProblemCode.PAYLOAD_EXTRA_KEY,
            "benign-extra-value",
        ),
        (
            _payload(script_sample="<script>secret-script</script>"),
            CspEvidenceProblemCode.PAYLOAD_SENSITIVE_KEY,
            "secret-script",
        ),
        (
            _payload(cookie="session=secret-cookie"),
            CspEvidenceProblemCode.PAYLOAD_SENSITIVE_KEY,
            "secret-cookie",
        ),
        (
            ('{"trace_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","trace_id":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}'),
            CspEvidenceProblemCode.PAYLOAD_DUPLICATE_KEY,
            "bbbbbbbb",
        ),
    ],
    ids=("malformed", "non-object", "extra", "script-sensitive", "cookie-sensitive", "duplicate"),
)
def test_malformed_nonobject_extra_and_sensitive_payloads_block_without_echo(
    payload_json: str,
    expected_code: CspEvidenceProblemCode,
    secret: str,
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    report = _run_rows(monkeypatch, evidence_engine, [_row(1, payload_json)])

    assert report.status is CspEvidenceStatus.BLOCKED
    assert report.counts.invalid_records == 1
    assert _problem_counts(report) == {expected_code: 1}
    assert secret not in report.to_json()


def test_payload_larger_than_r9_8_kib_is_blocked(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    payload_json = _payload(note="x" * (8 * 1024))

    report = _run_rows(monkeypatch, evidence_engine, [_row(1, payload_json)])

    assert report.status is CspEvidenceStatus.BLOCKED
    assert _problem_counts(report) == {CspEvidenceProblemCode.PAYLOAD_TOO_LARGE: 1}


@pytest.mark.parametrize(
    ("payload_json", "expected_code"),
    [
        (
            _payload(trace_id="not-a-record-trace"),
            CspEvidenceProblemCode.PAYLOAD_TRACE_INVALID,
        ),
        (
            _payload(disposition="enforce"),
            CspEvidenceProblemCode.PAYLOAD_DISPOSITION_INVALID,
        ),
    ],
    ids=("record-trace", "disposition"),
)
def test_invalid_record_trace_and_non_report_disposition_block(
    payload_json: str,
    expected_code: CspEvidenceProblemCode,
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    report = _run_rows(monkeypatch, evidence_engine, [_row(1, payload_json)])

    assert report.status is CspEvidenceStatus.BLOCKED
    assert _problem_counts(report) == {expected_code: 1}


def test_report_trace_is_independent_and_record_trace_never_leaks(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    record_trace = "1234567890abcdef1234567890abcdef"

    report = _run_rows(
        monkeypatch,
        evidence_engine,
        [_row(1, _payload(trace_id=record_trace))],
        catalog=_catalog(_catalog_entry()),
    )

    assert report.trace_id == REPORT_TRACE_ID
    assert report.trace_id != record_trace
    assert record_trace not in report.to_json()


def test_blocking_problem_wins_over_synthetic_insufficiency(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    report = _run_rows(
        monkeypatch,
        evidence_engine,
        [_row(1, "{malformed")],
        context=_context(accepted=1, evidence_source="synthetic"),
    )

    assert report.status is CspEvidenceStatus.BLOCKED
    assert set(_problem_counts(report)) == {
        CspEvidenceProblemCode.PAYLOAD_MALFORMED_JSON,
        CspEvidenceProblemCode.SYNTHETIC_EVIDENCE,
    }


def test_query_failure_has_highest_priority_and_omits_exception_text(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    leaked_exception = "https://user:secret@db.example.com/private?token=credential"

    def fail_query(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise RuntimeError(leaked_exception)

    monkeypatch.setattr(csp_evidence, "_query_page", fail_query)

    report = run_csp_evidence(
        evidence_engine,
        _context(accepted=1, evidence_source="synthetic"),
        _catalog(_catalog_entry(retest="pending")),
        trace_id=REPORT_TRACE_ID,
        now=NOW,
    )

    all_output = report.to_json() + caplog.text
    assert report.status is CspEvidenceStatus.FAILED
    assert report.error_type == "RuntimeError"
    assert _problem_counts(report) == {CspEvidenceProblemCode.QUERY_FAILED: 1}
    assert leaked_exception not in all_output
    assert "db.example.com" not in all_output
    assert "credential" not in all_output


def test_query_is_start_inclusive_end_exclusive_and_filters_log_type(
    evidence_engine: Engine,
):
    csp_evidence._metadata.create_all(evidence_engine)
    payload = _payload()
    with evidence_engine.begin() as connection:
        connection.execute(
            csp_evidence._frontend_logs.insert(),
            [
                {
                    "id": 1,
                    "type": "csp-violation",
                    "payload_json": payload,
                    "environment": "production",
                    "release": RELEASE,
                    "created_at": WINDOW_START - timedelta(microseconds=1),
                },
                {
                    "id": 2,
                    "type": "csp-violation",
                    "payload_json": payload,
                    "environment": "production",
                    "release": RELEASE,
                    "created_at": WINDOW_START,
                },
                {
                    "id": 3,
                    "type": "frontend-error",
                    "payload_json": payload,
                    "environment": "production",
                    "release": RELEASE,
                    "created_at": WINDOW_START + timedelta(days=1),
                },
                {
                    "id": 4,
                    "type": "csp-violation",
                    "payload_json": payload,
                    "environment": "production",
                    "release": RELEASE,
                    "created_at": WINDOW_END - timedelta(microseconds=1),
                },
                {
                    "id": 5,
                    "type": "csp-violation",
                    "payload_json": payload,
                    "environment": "production",
                    "release": RELEASE,
                    "created_at": WINDOW_END,
                },
            ],
        )

    report = run_csp_evidence(
        evidence_engine,
        _context(accepted=2),
        _catalog(_catalog_entry()),
        trace_id=REPORT_TRACE_ID,
        now=NOW,
    )

    assert report.status is CspEvidenceStatus.READY_FOR_REVIEW
    assert report.counts.scanned_records == 2
    assert report.counts.target_records == 2
    assert report.aggregates[0].count == 2


def test_50001st_row_truncates_at_50000_with_stable_code(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    page_limits: list[int] = []
    key = AggregateKey(
        RouteCategory.PRODUCT_DETAIL,
        DirectiveCategory.SCRIPT_SRC_ELEM,
        BlockedSourceCategory.INLINE,
    )

    def query_page(
        connection: Any,
        context: Any,
        last_id: int,
        *,
        page_limit: int = csp_evidence.CSP_EVIDENCE_PAGE_SIZE,
    ) -> list[dict[str, Any]]:
        del connection, context
        page_limits.append(page_limit)
        final_id = min(50_001, last_id + page_limit)
        return [_row(row_id, "{}") for row_id in range(last_id + 1, final_id + 1)]

    monkeypatch.setattr(csp_evidence, "_query_page", query_page)
    monkeypatch.setattr(
        csp_evidence,
        "_validate_payload",
        lambda payload_json, context: csp_evidence._ValidatedPayload(key=key, problems=()),
    )

    report = run_csp_evidence(
        evidence_engine,
        _context(accepted=50_000, received=50_001),
        _catalog(_catalog_entry()),
        trace_id=REPORT_TRACE_ID,
        now=NOW,
    )

    assert report.status is CspEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert report.counts.scanned_records == 50_000
    assert report.counts.classified_records == 50_000
    assert report.counts.truncated is True
    assert _problem_counts(report) == {CspEvidenceProblemCode.ROW_LIMIT_EXCEEDED: 1}
    assert max(page_limits) == 500
    assert page_limits[-1] == 1


def test_501st_aggregate_group_truncates_at_500(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    routes = [item for item in RouteCategory if item is not RouteCategory.UNKNOWN]
    directives = [item for item in DirectiveCategory if item is not DirectiveCategory.UNKNOWN]
    sources = [item for item in BlockedSourceCategory if item is not BlockedSourceCategory.UNKNOWN]
    keys = [
        AggregateKey(route, directive, source) for route, directive, source in product(routes, directives, sources)
    ][:501]
    rows = [_row(index + 1, str(index)) for index in range(501)]
    entries = [
        _catalog_entry(
            catalog_id=f"group-{index:03d}",
            route=key.route_category.value,
            directive=key.directive_category.value,
            source=key.blocked_source_category.value,
        )
        for index, key in enumerate(keys[:500])
    ]
    _install_rows(monkeypatch, rows)
    monkeypatch.setattr(
        csp_evidence,
        "_validate_payload",
        lambda payload_json, context: csp_evidence._ValidatedPayload(
            key=keys[int(payload_json)],
            problems=(),
        ),
    )

    report = run_csp_evidence(
        evidence_engine,
        _context(accepted=501, received=501),
        _catalog(*entries),
        trace_id=REPORT_TRACE_ID,
        now=NOW,
    )

    assert report.status is CspEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert report.counts.scanned_records == 501
    assert report.counts.classified_records == 500
    assert report.counts.aggregate_groups == 500
    assert report.counts.known_groups == 500
    assert report.counts.truncated is True
    assert _problem_counts(report) == {CspEvidenceProblemCode.GROUP_LIMIT_EXCEEDED: 1}


def test_exact_30_second_runtime_limit_truncates_before_conclusion(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    _install_rows(monkeypatch, [])
    times = iter((0.0, 0.0, 30.0))

    report = run_csp_evidence(
        evidence_engine,
        _context(accepted=0, received=1),
        _catalog(),
        trace_id=REPORT_TRACE_ID,
        now=NOW,
        clock=lambda: next(times),
    )

    assert report.status is CspEvidenceStatus.INSUFFICIENT_EVIDENCE
    assert report.counts.truncated is True
    assert _problem_counts(report)[CspEvidenceProblemCode.RUNTIME_LIMIT_EXCEEDED] == 1
    query_check = next(check for check in report.checks if check.code is CspEvidenceCheckCode.QUERY_COMPLETE)
    assert query_check.status is CspEvidenceCheckStatus.FAILED


def test_report_size_guard_accepts_256_kib_and_fails_closed_above_it(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    context = _context(accepted=0, received=1)
    catalog = _catalog()

    class SizedReport:
        def __init__(self, size: int):
            self.size = size

        def to_json(self) -> str:
            return "x" * self.size

    exact_report = SizedReport(csp_evidence.CSP_EVIDENCE_REPORT_MAX_BYTES)
    monkeypatch.setattr(csp_evidence, "_run_csp_evidence", lambda *args, **kwargs: exact_report)

    accepted = run_csp_evidence(
        evidence_engine,
        context,
        catalog,
        trace_id=REPORT_TRACE_ID,
        now=NOW,
    )

    assert accepted is exact_report
    oversized_report = SizedReport(csp_evidence.CSP_EVIDENCE_REPORT_MAX_BYTES + 1)
    monkeypatch.setattr(csp_evidence, "_run_csp_evidence", lambda *args, **kwargs: oversized_report)

    failed = run_csp_evidence(
        evidence_engine,
        context,
        catalog,
        trace_id=REPORT_TRACE_ID,
        now=NOW,
    )

    assert csp_evidence.CSP_EVIDENCE_REPORT_MAX_BYTES == 256 * 1024
    assert failed.status is CspEvidenceStatus.FAILED
    assert failed.error_type == "CspEvidenceReportSizeError"
    assert _problem_counts(failed) == {CspEvidenceProblemCode.REPORT_SIZE_EXCEEDED: 1}
    bounded_check = next(check for check in failed.checks if check.code is CspEvidenceCheckCode.REPORT_BOUNDED)
    assert bounded_check.status is CspEvidenceCheckStatus.FAILED


def test_aggregates_and_catalog_output_are_deterministic_and_sensitive_values_never_leak(
    evidence_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
):
    sensitive_values = (
        "app.example.com",
        "SECRET-CONTRACT",
        "outside-private.example.net",
        "private-library.js",
        "source-private.example.net",
        "runtime-secret.js",
        "referrer-private.example.net",
        "record-a-trace",
    )
    payloads = [
        _payload(
            trace_id="1" * 32,
            document_url=f"{EXPECTED_ORIGIN}/workspace",
            blocked_url="https://outside-private.example.net/private-library.js",
            directive="connect-src",
            source_file="https://source-private.example.net/runtime-secret.js",
            referrer="https://referrer-private.example.net/previous",
        ),
        _payload(
            trace_id="2" * 32,
            document_url=f"{EXPECTED_ORIGIN}/products/SECRET-CONTRACT",
            blocked_url="inline",
            directive="script-src-elem",
        ),
        _payload(
            trace_id="3" * 32,
            document_url=f"{EXPECTED_ORIGIN}/",
            blocked_url="data",
            directive="style-src",
        ),
    ]
    entries = [
        _catalog_entry(
            catalog_id="workspace-connect-external",
            route="workspace",
            directive="connect_src",
            source="external_untrusted",
        ),
        _catalog_entry(),
        _catalog_entry(
            catalog_id="home-style-data",
            route="home",
            directive="style_src",
            source="data",
        ),
    ]
    context = _context(accepted=3, received=3)
    catalog = _catalog(*reversed(entries))

    first = _run_rows(
        monkeypatch,
        evidence_engine,
        [_row(index + 1, payload) for index, payload in enumerate(payloads)],
        context=context,
        catalog=catalog,
    )
    second = _run_rows(
        monkeypatch,
        evidence_engine,
        [_row(index + 1, payload) for index, payload in enumerate(reversed(payloads))],
        context=context,
        catalog=catalog,
    )

    assert first.status is CspEvidenceStatus.READY_FOR_REVIEW
    assert first.to_json() == second.to_json()
    aggregate_keys = [
        (
            item.key.route_category.value,
            item.key.directive_category.value,
            item.key.blocked_source_category.value,
        )
        for item in first.aggregates
    ]
    assert aggregate_keys == sorted(aggregate_keys)
    serialized = first.to_json()
    for sensitive in sensitive_values:
        assert sensitive not in serialized
    for record_trace in ("1" * 32, "2" * 32, "3" * 32):
        assert record_trace not in serialized
    assert len(serialized.encode("utf-8")) <= csp_evidence.CSP_EVIDENCE_REPORT_MAX_BYTES
