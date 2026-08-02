"""Focused tests for the low-cost K-line storage overview."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from services.kline_storage import (
    KlineStorageOverviewCache,
    collect_kline_storage_overview,
    get_kline_storage_overview,
)

NOW = datetime(2026, 8, 2, 6, 30, tzinfo=UTC)


class FakeResult:
    def __init__(self, *, scalar: Any = None, rows: list[dict[str, Any]] | None = None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one(self) -> Any:
        return self._scalar

    def mappings(self) -> FakeResult:
        return self

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class FakePostgresConnection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def __enter__(self) -> FakePostgresConnection:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        if "kline_storage:overview_relation" in sql:
            return FakeResult(
                rows=[
                    {
                        "is_partitioned": True,
                        "row_estimate": 12_345,
                        "table_bytes": 10_000,
                        "index_bytes": 2_000,
                        "total_bytes": 12_000,
                    }
                ]
            )
        if "kline_storage:overview_partition_tree" in sql:
            return FakeResult(
                rows=[
                    {
                        "partition_name": f"kline_minute_{month.replace('-', '')}",
                        "partition_bound": (
                            f"FOR VALUES FROM ('{month}-01 00:00:00+00') "
                            f"TO ('{next_month}-01 00:00:00+00')"
                        ),
                    }
                    for month, next_month in (
                        ("2026-09", "2026-10"),
                        ("2026-10", "2026-11"),
                        ("2026-11", "2026-12"),
                    )
                ]
            )
        if "kline_storage:overview_last_collection" in sql:
            assert parameters == {
                "job_pattern": "sync_kline_%",
                "success_status": "success",
            }
            return FakeResult(scalar=datetime(2026, 8, 1, 12, 0, tzinfo=UTC))
        raise AssertionError(f"unexpected statement: {sql}")


class FakePostgresEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self) -> None:
        self.connection = FakePostgresConnection()

    def connect(self) -> FakePostgresConnection:
        return self.connection


def test_postgresql_overview_uses_catalog_estimate_without_count_scan():
    engine = FakePostgresEngine()

    data = collect_kline_storage_overview(engine, now=NOW).to_dict()

    assert data == {
        "dialect": "postgresql",
        "storage_bytes": {
            "table": 10_000,
            "indexes": 2_000,
            "total": 12_000,
        },
        "row_estimate": 12_345,
        "row_count": None,
        "partitioning_supported": True,
        "is_partitioned": True,
        "partition_count": 3,
        "future_coverage": {
            "required_months": ["2026-09", "2026-10", "2026-11"],
            "missing_months": [],
            "complete": True,
        },
        "last_collection_time": "2026-08-01T12:00:00Z",
        "collected_at": "2026-08-02T06:30:00Z",
    }
    assert all("count(*)" not in statement.casefold() for statement in engine.connection.statements)
    assert all("from kline_data" not in statement.casefold() for statement in engine.connection.statements)


def test_sqlite_overview_cache_expires_and_can_be_invalidated():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE kline_data (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                """
                CREATE TABLE data_ingestion_runs (
                    job_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at DATETIME NOT NULL,
                    finished_at DATETIME
                )
                """
            )
        )
        connection.execute(text("INSERT INTO kline_data (id) VALUES (1)"))

    current_time = [0.0]
    cache = KlineStorageOverviewCache(ttl_seconds=60, clock=lambda: current_time[0])

    first = get_kline_storage_overview(engine, now=NOW, cache=cache)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO kline_data (id) VALUES (2)"))
    cached = get_kline_storage_overview(engine, now=NOW, cache=cache)

    assert cached is first
    assert cached.to_dict()["row_count"] == 1
    assert cached.to_dict()["row_estimate"] is None
    assert cached.to_dict()["partitioning_supported"] is False

    current_time[0] = 61.0
    expired = get_kline_storage_overview(engine, now=NOW, cache=cache)
    assert expired.to_dict()["row_count"] == 2

    with engine.begin() as connection:
        connection.execute(text("INSERT INTO kline_data (id) VALUES (3)"))
    cache.invalidate(engine)

    refreshed = get_kline_storage_overview(engine, now=NOW, cache=cache)
    assert refreshed.to_dict()["row_count"] == 3
