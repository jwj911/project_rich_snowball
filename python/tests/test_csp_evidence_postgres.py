"""PostgreSQL and SQLite read-only integration coverage for R10 CSP evidence."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, event, select, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from models import FrontendLogDB
from services.csp_evidence import (
    BlockedSourceCategory,
    CatalogDecision,
    CspEvidenceStatus,
    DirectiveCategory,
    EvidenceEnvironment,
    EvidenceSource,
    RetestStatus,
    RouteCategory,
    WorkflowName,
    run_csp_evidence,
    validate_csp_evidence_context,
    validate_csp_violation_catalog,
)

_PG_URL = os.environ.get("_PYTEST_ORIGINAL_DATABASE_URL", "")
_IS_PG = _PG_URL.startswith("postgresql")
_RELEASE = "0123456789abcdef0123456789abcdef01234567"
_OTHER_RELEASE = "89abcdef0123456789abcdef0123456789abcdef"
_DML_PATTERN = re.compile(r"^(?:insert|update|delete|merge|truncate|alter|drop|create)\b", re.IGNORECASE)
_PROJECTION_COLUMNS = [
    "id",
    "payload_json",
    "environment",
    "release",
    "created_at",
]
_SNAPSHOT_COLUMNS = (
    FrontendLogDB.id,
    FrontendLogDB.user_id,
    FrontendLogDB.log_type,
    FrontendLogDB.level,
    FrontendLogDB.url,
    FrontendLogDB.user_agent,
    FrontendLogDB.release,
    FrontendLogDB.environment,
    FrontendLogDB.payload_json,
    FrontendLogDB.created_at,
)


@dataclass(frozen=True)
class _EvidenceRows:
    engine: Engine
    row_ids: tuple[int, ...]
    target_id: int
    origin: str
    window_start: datetime
    window_end: datetime
    snapshot: tuple[tuple[Any, ...], ...]


def _payload(document_url: str) -> str:
    return json.dumps(
        {
            "trace_id": uuid.uuid4().hex,
            "document_url": document_url,
            "blocked_url": "inline",
            "effective_directive": "script-src-elem",
            "disposition": "report",
        },
        sort_keys=True,
    )


def _build_context(rows: _EvidenceRows, *, accepted: int):
    return validate_csp_evidence_context(
        {
            "schema_version": 1,
            "evidence_source": EvidenceSource.TARGET_ENVIRONMENT.value,
            "environment": EvidenceEnvironment.PRODUCTION.value,
            "release": _RELEASE,
            "window_start": rows.window_start.isoformat().replace("+00:00", "Z"),
            "window_end": rows.window_end.isoformat().replace("+00:00", "Z"),
            "sample_rate": 1,
            "complete_business_cycle": True,
            "workflows": {name.value: "passed" for name in WorkflowName},
            "metrics": {
                "business_http_requests": 1,
                "csp_outcomes": {
                    "received": accepted,
                    "accepted": accepted,
                    "sampled": 0,
                    "rejected": 0,
                    "rate_limited": 0,
                    "persist_failed": 0,
                },
            },
            "expected_document_origins": [rows.origin],
            "trusted_source_origins": [],
        }
    )


def _build_catalog():
    return validate_csp_violation_catalog(
        {
            "schema_version": 1,
            "entries": [
                {
                    "catalog_id": "inline-product-script",
                    "route_category": RouteCategory.PRODUCT_DETAIL.value,
                    "directive_category": DirectiveCategory.SCRIPT_SRC_ELEM.value,
                    "blocked_source_category": BlockedSourceCategory.INLINE.value,
                    "owner_role": "frontend-security",
                    "decision": CatalogDecision.REMEDIATE_BEFORE_S2.value,
                    "retest_status": RetestStatus.PASSED.value,
                }
            ],
        }
    )


def _snapshot(engine: Engine, row_ids: tuple[int, ...]) -> tuple[tuple[Any, ...], ...]:
    with engine.connect() as connection:
        rows = connection.execute(
            select(*_SNAPSHOT_COLUMNS).where(FrontendLogDB.id.in_(row_ids)).order_by(FrontendLogDB.id)
        ).all()
    return tuple(tuple(row) for row in rows)


def _normalize_sql(statement: str) -> str:
    return " ".join(statement.split()).lower()


def _is_evidence_select(statement: str) -> bool:
    normalized = _normalize_sql(statement)
    return normalized.startswith("select ") and " from frontend_logs " in normalized and "frontend_logs.payload_json" in normalized


def _assert_bounded_projection(statement: str, parameters: Any) -> None:
    normalized = _normalize_sql(statement)
    projection = normalized.split(" from frontend_logs ", maxsplit=1)[0]
    assert re.findall(r"frontend_logs\.([a-z_]+)", projection) == _PROJECTION_COLUMNS
    assert "frontend_logs.type =" in normalized
    assert "frontend_logs.created_at >=" in normalized
    assert "frontend_logs.created_at <" in normalized
    assert "frontend_logs.id >" in normalized
    assert "order by frontend_logs.id" in normalized
    assert " limit " in normalized
    values = parameters.values() if isinstance(parameters, Mapping) else parameters
    assert 500 in values


@pytest.fixture
def pg_frontend_logs():
    """Create unique PostgreSQL FrontendLogDB rows and clean them outside R10."""
    if not _IS_PG:
        pytest.skip("R10 PostgreSQL read-only integration requires _PYTEST_ORIGINAL_DATABASE_URL")

    suffix = uuid.uuid4().hex
    origin = f"https://r10-csp-{suffix}.example.test"
    urls = tuple(f"{origin}/fixture/{index}" for index in range(4))
    window_start = datetime(2099, 1, 1, tzinfo=UTC) + timedelta(microseconds=int(suffix[:8], 16))
    window_end = window_start + timedelta(microseconds=1)
    document_url = f"{origin}/products/AU"
    engine = create_engine(_PG_URL, pool_pre_ping=True)

    try:
        with Session(engine) as session:
            rows = [
                FrontendLogDB(
                    log_type="csp-violation",
                    level="warning",
                    url=urls[0],
                    user_agent="r10-postgres-fixture",
                    payload_json=_payload(document_url),
                    environment="production",
                    release=_RELEASE,
                    created_at=window_start,
                ),
                FrontendLogDB(
                    log_type="csp-violation",
                    level="warning",
                    url=urls[1],
                    user_agent="r10-postgres-fixture",
                    payload_json=_payload(document_url),
                    environment="production",
                    release=_OTHER_RELEASE,
                    created_at=window_start,
                ),
                FrontendLogDB(
                    log_type="csp-violation",
                    level="warning",
                    url=urls[2],
                    user_agent="r10-postgres-fixture",
                    payload_json=_payload(document_url),
                    environment="staging",
                    release=_RELEASE,
                    created_at=window_start,
                ),
                FrontendLogDB(
                    log_type="error",
                    level="error",
                    url=urls[3],
                    user_agent="r10-postgres-fixture",
                    payload_json=_payload(document_url),
                    environment="production",
                    release=_RELEASE,
                    created_at=window_start,
                ),
            ]
            session.add_all(rows)
            session.commit()
            row_ids = tuple(row.id for row in rows)

        yield _EvidenceRows(
            engine=engine,
            row_ids=row_ids,
            target_id=row_ids[0],
            origin=origin,
            window_start=window_start,
            window_end=window_end,
            snapshot=_snapshot(engine, row_ids),
        )
    finally:
        with Session(engine) as session:
            session.query(FrontendLogDB).filter(FrontendLogDB.url.in_(urls)).delete(synchronize_session=False)
            session.commit()
            assert session.query(FrontendLogDB).filter(FrontendLogDB.url.in_(urls)).count() == 0
        engine.dispose()


def test_postgres_r10_query_is_bounded_scoped_and_read_only(pg_frontend_logs):
    rows = pg_frontend_logs
    statements: list[str] = []
    evidence_queries: list[tuple[str, Any]] = []
    server_settings: list[tuple[str, bool]] = []

    def capture_settings(connection, _cursor, statement, parameters, _context, _executemany):
        statements.append(_normalize_sql(statement))
        if not _is_evidence_select(statement):
            return
        evidence_queries.append((statement, parameters))
        probe = connection.connection.driver_connection.cursor()
        try:
            probe.execute(
                "SELECT current_setting('transaction_read_only'), "
                "current_setting('statement_timeout')::interval = interval '30 seconds'"
            )
            server_settings.append(tuple(probe.fetchone()))
        finally:
            probe.close()

    event.listen(rows.engine, "before_cursor_execute", capture_settings)
    try:
        report = run_csp_evidence(rows.engine, _build_context(rows, accepted=3), _build_catalog())
    finally:
        event.remove(rows.engine, "before_cursor_execute", capture_settings)

    assert rows.engine.dialect.name == "postgresql"
    assert report.status is CspEvidenceStatus.BLOCKED
    assert report.context.environment is EvidenceEnvironment.PRODUCTION
    assert report.context.release == _RELEASE
    assert report.counts.scanned_records == 3
    assert report.counts.target_records == 1
    assert report.counts.scope_mismatch_records == 2
    assert report.counts.classified_records == 1
    assert report.counts.known_records == 1
    assert [aggregate.to_dict() for aggregate in report.aggregates] == [
        {
            "route_category": "product_detail",
            "directive_category": "script_src_elem",
            "blocked_source_category": "inline",
            "count": 1,
        }
    ]

    assert len(evidence_queries) == 1
    _assert_bounded_projection(*evidence_queries[0])
    assert server_settings == [("on", True)]
    assert "set transaction read only" in statements
    assert "set local statement_timeout = 30000" in statements
    assert all(_DML_PATTERN.match(statement) is None for statement in statements)
    assert _snapshot(rows.engine, rows.row_ids) == rows.snapshot


def test_sqlite_query_only_rejects_writes_and_preserves_caller_transaction(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'r10-evidence.db'}")
    FrontendLogDB.__table__.create(engine)
    suffix = uuid.uuid4().hex
    origin = f"https://r10-sqlite-{suffix}.example.test"
    window_start = datetime(2098, 1, 1, tzinfo=UTC)
    document_url = f"{origin}/products/AU"

    try:
        with Session(engine) as session:
            row = FrontendLogDB(
                log_type="csp-violation",
                level="warning",
                url=f"{origin}/fixture",
                user_agent="r10-sqlite-fixture",
                payload_json=_payload(document_url),
                environment="production",
                release=_RELEASE,
                created_at=window_start,
            )
            session.add(row)
            session.commit()
            row_id = row.id

        rows = _EvidenceRows(
            engine=engine,
            row_ids=(row_id,),
            target_id=row_id,
            origin=origin,
            window_start=window_start,
            window_end=window_start + timedelta(microseconds=1),
            snapshot=_snapshot(engine, (row_id,)),
        )
        statements: list[str] = []
        evidence_queries: list[tuple[str, Any]] = []
        query_only_values: list[int] = []

        def reject_write(connection, _cursor, statement, parameters, _context, _executemany):
            statements.append(_normalize_sql(statement))
            if not _is_evidence_select(statement):
                return
            evidence_queries.append((statement, parameters))
            probe = connection.connection.driver_connection.cursor()
            try:
                probe.execute("PRAGMA query_only")
                query_only_values.append(probe.fetchone()[0])
                with pytest.raises(sqlite3.OperationalError):
                    probe.execute(
                        "UPDATE frontend_logs SET environment = 'tampered' WHERE id = ?",
                        (row_id,),
                    )
            finally:
                probe.close()

        event.listen(engine, "before_cursor_execute", reject_write)
        try:
            report = run_csp_evidence(engine, _build_context(rows, accepted=1), _build_catalog())
        finally:
            event.remove(engine, "before_cursor_execute", reject_write)

        assert report.status is CspEvidenceStatus.READY_FOR_REVIEW
        assert report.counts.scanned_records == 1
        assert report.counts.target_records == 1
        assert query_only_values == [1]
        assert len(evidence_queries) == 1
        _assert_bounded_projection(*evidence_queries[0])
        assert all(_DML_PATTERN.match(statement) is None for statement in statements)
        assert _snapshot(engine, rows.row_ids) == rows.snapshot

        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA query_only")).scalar_one() == 0

        with engine.connect() as connection:
            caller_transaction = connection.begin()
            connection.execute(
                update(FrontendLogDB).where(FrontendLogDB.id == row_id).values(level="caller-pending")
            )

            failed_report = run_csp_evidence(connection, _build_context(rows, accepted=1), _build_catalog())

            assert failed_report.status is CspEvidenceStatus.FAILED
            assert failed_report.error_type == "CspEvidenceCollectionError"
            assert caller_transaction.is_active
            assert connection.execute(
                select(FrontendLogDB.level).where(FrontendLogDB.id == row_id)
            ).scalar_one() == "caller-pending"
            caller_transaction.rollback()

        assert _snapshot(engine, rows.row_ids) == rows.snapshot
    finally:
        engine.dispose()
