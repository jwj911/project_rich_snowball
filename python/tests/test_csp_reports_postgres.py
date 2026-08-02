"""PostgreSQL integration coverage for R9 CSP report persistence."""

from __future__ import annotations

import json
import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import FrontendLogDB
from routers.frontend_logs import _persist_csp_reports

_PG_URL = os.environ.get("_PYTEST_ORIGINAL_DATABASE_URL", "")
_IS_PG = _PG_URL.startswith("postgresql")

if _IS_PG:
    _pg_engine = create_engine(_PG_URL, pool_pre_ping=True)
    _PgSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_pg_engine)
else:
    _pg_engine = None
    _PgSessionLocal = None

pytestmark = pytest.mark.skipif(
    not _IS_PG,
    reason="R9 CSP persistence integration requires PostgreSQL DATABASE_URL",
)


@pytest.fixture
def pg_csp_batch():
    """Build unique CSP rows and remove them from PostgreSQL after the test."""
    assert _pg_engine is not None
    assert _PgSessionLocal is not None

    suffix = uuid.uuid4().hex
    urls = [
        f"https://r9-csp-{suffix}.example.test/products/AU",
        f"https://r9-csp-{suffix}.example.test/products/AG",
    ]
    prepared_reports = [
        (
            uuid.uuid4().hex,
            {
                "document_url": url,
                "blocked_url": "inline",
                "effective_directive": "script-src-elem",
                "disposition": "report",
            },
        )
        for url in urls
    ]
    db = _PgSessionLocal()

    try:
        yield db, urls, prepared_reports
    finally:
        db.rollback()
        db.query(FrontendLogDB).filter(FrontendLogDB.url.in_(urls)).delete(synchronize_session=False)
        db.commit()
        assert db.query(FrontendLogDB).filter(FrontendLogDB.url.in_(urls)).count() == 0
        db.close()
        _pg_engine.dispose()


def test_postgres_persists_csp_batch_and_independent_trace_ids(pg_csp_batch):
    db, urls, prepared_reports = pg_csp_batch

    error_type = _persist_csp_reports(db, prepared_reports)

    assert error_type is None
    assert db.bind.dialect.name == "postgresql"
    rows = db.query(FrontendLogDB).filter(FrontendLogDB.url.in_(urls)).order_by(FrontendLogDB.url).all()
    assert len(rows) == 2
    assert {row.url for row in rows} == set(urls)
    payloads = [json.loads(row.payload_json) for row in rows]
    assert {payload["trace_id"] for payload in payloads} == {trace_id for trace_id, _ in prepared_reports}
    assert all(row.log_type == "csp-violation" and row.user_id is None for row in rows)
