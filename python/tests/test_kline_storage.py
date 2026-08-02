"""Focused tests for the read-only K-line storage preflight."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from scripts import kline_storage_preflight as kline_storage_cli
from services.kline_storage import (
    KLINE_MINUTE_QUERY_P99_THRESHOLD_MS,
    KLINE_ROW_COUNT_THRESHOLD,
    KLINE_TOTAL_BYTES_THRESHOLD,
    KlineStorageCheckCode,
    KlineStorageCheckStatus,
    KlineStorageStatus,
    run_kline_storage_preflight,
)

DATABASE_PASSWORD = "database-password-must-not-leak"
PROVIDER_TOKEN = "provider-token-must-not-leak"
SQL_PARAMETER_VALUE = 987_654_321
NOW = datetime(2026, 8, 2, 6, 30, tzinfo=UTC)


class FakeResult:
    def __init__(self, *, scalar: Any = None, rows: list[dict[str, Any]] | None = None):
        self._scalar = scalar
        self._rows = rows or []

    def scalar_one(self) -> Any:
        return self._scalar

    def mappings(self) -> FakeResult:
        return self

    def one(self) -> dict[str, Any]:
        if len(self._rows) != 1:
            raise AssertionError(f"expected one row, received {len(self._rows)}")
        return self._rows[0]

    def all(self) -> list[dict[str, Any]]:
        return self._rows

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None


class FakePostgresConnection:
    def __init__(
        self,
        *,
        row_count: int,
        total_bytes: int,
        fail_marker: str | None = None,
    ):
        self.row_count = row_count
        self.total_bytes = total_bytes
        self.fail_marker = fail_marker
        self.statements: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self) -> FakePostgresConnection:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def execute(self, statement: Any, parameters: dict[str, Any] | None = None) -> FakeResult:
        sql = str(statement)
        self.statements.append((sql, parameters or {}))
        if self.fail_marker and self.fail_marker in sql:
            raise RuntimeError(
                f"failed with postgresql://user:{DATABASE_PASSWORD}@db.example.com/app TUSHARE_TOKEN={PROVIDER_TOKEN}"
            )
        if "kline_storage:postgres_version" in sql:
            return FakeResult(scalar="16.4")
        if "kline_storage:postgres_sizes" in sql:
            return FakeResult(
                rows=[
                    {
                        "table_bytes": max(self.total_bytes - 1024, 0),
                        "index_bytes": min(self.total_bytes, 1024),
                        "total_bytes": self.total_bytes,
                    }
                ]
            )
        if "kline_storage:period_stats" in sql:
            return FakeResult(
                rows=[
                    {
                        "period": "1m",
                        "row_count": self.row_count,
                        "min_trading_time": datetime(2026, 7, 1, tzinfo=UTC),
                        "max_trading_time": datetime(2026, 8, 1, tzinfo=UTC),
                    }
                ]
            )
        if "kline_storage:partition_state" in sql:
            return FakeResult(rows=[{"is_partitioned": True}])
        if "kline_storage:partition_tree" in sql:
            return FakeResult(
                rows=[
                    {
                        "partition_name": "kline_minute",
                        "partition_bound": "FOR VALUES IN ('1m', '1')",
                    },
                    {
                        "partition_name": "kline_minute_202609",
                        "partition_bound": ("FOR VALUES FROM ('2026-09-01 00:00:00+00') TO ('2026-10-01 00:00:00+00')"),
                    },
                    {
                        "partition_name": "kline_minute_202611",
                        "partition_bound": ("FOR VALUES FROM ('2026-11-01 00:00:00+00') TO ('2026-12-01 00:00:00+00')"),
                    },
                ]
            )
        if "kline_storage:minute_sample" in sql:
            return FakeResult(
                rows=[
                    {
                        "variety_id": 123_456_789,
                        "contract_id": SQL_PARAMETER_VALUE,
                        "period": "1m",
                        "min_trading_time": datetime(2026, 7, 1, tzinfo=UTC),
                        "max_trading_time": datetime(2026, 8, 1, tzinfo=UTC),
                        "row_count": self.row_count,
                    }
                ]
            )
        if "kline_storage:explain_" in sql:
            return FakeResult(scalar=_raw_plan())
        raise AssertionError(f"unexpected statement: {sql}")


class FakePostgresEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(
        self,
        *,
        row_count: int = 10_000,
        total_bytes: int = 1024**3,
        fail_marker: str | None = None,
    ):
        self.connection = FakePostgresConnection(
            row_count=row_count,
            total_bytes=total_bytes,
            fail_marker=fail_marker,
        )
        self.disposed = False

    def connect(self) -> FakePostgresConnection:
        return self.connection

    def dispose(self) -> None:
        self.disposed = True


def _raw_plan() -> list[dict[str, Any]]:
    return [
        {
            "Plan": {
                "Node Type": "Limit",
                "Startup Cost": 0.42,
                "Total Cost": 18.5,
                "Plan Rows": 1000,
                "Plans": [
                    {
                        "Node Type": "Index Scan",
                        "Relation Name": "kline_data",
                        "Index Name": "idx_kline_contract_period_time",
                        "Index Cond": f"(contract_id = {SQL_PARAMETER_VALUE})",
                        "Filter": (
                            f"postgresql://user:{DATABASE_PASSWORD}@db.example.com/app TUSHARE_TOKEN={PROVIDER_TOKEN}"
                        ),
                    }
                ],
            },
            "Planning Time": 0.25,
        }
    ]


def _run_postgres(
    *,
    row_count: int = 10_000,
    total_bytes: int = 1024**3,
    p99_ms: float | None = 100.0,
):
    engine = FakePostgresEngine(row_count=row_count, total_bytes=total_bytes)
    report = run_kline_storage_preflight(
        engine,
        minute_query_p99_ms=p99_ms,
        now=NOW,
        sensitive_values=(DATABASE_PASSWORD, PROVIDER_TOKEN),
    )
    return report, engine


def test_threshold_constants_and_stable_report_model():
    report, _ = _run_postgres()

    assert KLINE_ROW_COUNT_THRESHOLD == 100_000_000
    assert KLINE_TOTAL_BYTES_THRESHOLD == 100 * 1024**3
    assert KLINE_MINUTE_QUERY_P99_THRESHOLD_MS == 500.0
    assert report.status is KlineStorageStatus.NOT_REQUIRED
    assert report.gate_passed is True
    assert [check.code for check in report.checks] == list(KlineStorageCheckCode)
    assert report.to_dict()["thresholds"] == {
        "row_count": 100_000_000,
        "total_bytes": 107_374_182_400,
        "minute_query_p99_ms": 500.0,
    }


@pytest.mark.parametrize(
    ("row_count", "total_bytes", "p99_ms", "trigger_code"),
    [
        (KLINE_ROW_COUNT_THRESHOLD, 1024**3, 100.0, KlineStorageCheckCode.ROW_COUNT_THRESHOLD),
        (10_000, KLINE_TOTAL_BYTES_THRESHOLD, 100.0, KlineStorageCheckCode.TOTAL_BYTES_THRESHOLD),
        (
            10_000,
            1024**3,
            KLINE_MINUTE_QUERY_P99_THRESHOLD_MS,
            KlineStorageCheckCode.MINUTE_QUERY_P99_THRESHOLD,
        ),
    ],
)
def test_reaching_any_threshold_recommends_shadow_migration(
    row_count: int,
    total_bytes: int,
    p99_ms: float,
    trigger_code: KlineStorageCheckCode,
):
    report, _ = _run_postgres(
        row_count=row_count,
        total_bytes=total_bytes,
        p99_ms=p99_ms,
    )

    assert report.status is KlineStorageStatus.RECOMMENDED
    assert report.trigger_codes == (trigger_code,)
    triggered = [check.code for check in report.checks if check.status is KlineStorageCheckStatus.TRIGGERED]
    assert triggered == [trigger_code]


def test_missing_external_p99_is_inconclusive_instead_of_inventing_latency():
    report, _ = _run_postgres(p99_ms=None)

    assert report.status is KlineStorageStatus.INCONCLUSIVE
    p99_check = next(check for check in report.checks if check.code is KlineStorageCheckCode.MINUTE_QUERY_P99_THRESHOLD)
    assert p99_check.status is KlineStorageCheckStatus.NOT_AVAILABLE


def test_postgres_collects_exact_aggregates_partition_gaps_and_redacted_plan_summary():
    report, engine = _run_postgres()

    payload = report.to_dict()
    evidence = payload["evidence"]
    assert evidence["database_version"] == "16.4"
    assert evidence["row_count"] == 10_000
    assert evidence["row_count_kind"] == "exact_grouped_count"
    assert evidence["storage_bytes"] == {
        "table": 1_073_740_800,
        "indexes": 1024,
        "total": 1_073_741_824,
    }
    assert evidence["periods"] == [
        {
            "period": "1m",
            "row_count": 10_000,
            "min_trading_time": "2026-07-01T00:00:00Z",
            "max_trading_time": "2026-08-01T00:00:00Z",
        }
    ]
    assert evidence["partitioning"] == {
        "supported": True,
        "is_partitioned": True,
        "partition_count": 3,
        "required_future_months": ["2026-09", "2026-10", "2026-11"],
        "missing_future_months": ["2026-10"],
    }
    assert len(evidence["minute_query"]["plans"]) == 2
    assert evidence["minute_query"]["plans"][0] == {
        "query_code": "KLINE_VARIETY_MINUTE_RANGE",
        "root_node_type": "Limit",
        "node_type_counts": {"Index Scan": 1, "Limit": 1},
        "relation_names": ["kline_data"],
        "index_names": ["idx_kline_contract_period_time"],
        "startup_cost": 0.42,
        "total_cost": 18.5,
        "plan_rows": 1000,
        "subplans_removed": 0,
        "planning_time_ms": 0.25,
    }

    serialized = report.to_json()
    for secret in (DATABASE_PASSWORD, PROVIDER_TOKEN, str(SQL_PARAMETER_VALUE)):
        assert secret not in serialized
    assert "Index Cond" not in serialized
    assert "Filter" not in serialized
    _assert_only_read_only_statements(engine.connection.statements)


def test_each_run_has_an_independent_trace_id():
    first, _ = _run_postgres()
    second, _ = _run_postgres()

    assert first.trace_id != second.trace_id
    assert len(first.trace_id) == len(second.trace_id) == 32


def test_collection_failure_keeps_stable_code_and_omits_exception_message():
    engine = FakePostgresEngine(fail_marker="kline_storage:postgres_sizes")

    report = run_kline_storage_preflight(
        engine,
        minute_query_p99_ms=100.0,
        sensitive_values=(DATABASE_PASSWORD, PROVIDER_TOKEN),
    )

    serialized = report.to_json()
    assert report.status is KlineStorageStatus.FAILED
    assert report.checks[0].code is KlineStorageCheckCode.COLLECTION
    assert report.checks[0].status is KlineStorageCheckStatus.FAILED
    assert report.error_type == "RuntimeError"
    assert "postgresql://" not in serialized
    assert DATABASE_PASSWORD not in serialized
    assert PROVIDER_TOKEN not in serialized


def test_sqlite_collects_basic_stats_without_postgres_sql_or_side_effects():
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE kline_data (
                    period TEXT NOT NULL,
                    trading_time TEXT NOT NULL,
                    open_price REAL NOT NULL,
                    high_price REAL NOT NULL,
                    low_price REAL NOT NULL,
                    close_price REAL NOT NULL,
                    volume INTEGER NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO kline_data (
                    period, trading_time, open_price, high_price,
                    low_price, close_price, volume
                ) VALUES
                    ('1m', '2026-08-01T01:00:00Z', 12345.6789, 12346, 12344, 12345, 99),
                    ('1m', '2026-08-01T01:01:00Z', 22345.6789, 22346, 22344, 22345, 88),
                    ('D', '2026-08-01T00:00:00Z', 32345.6789, 32346, 32344, 32345, 77)
                """
            )
        )

    statements: list[str] = []

    def record_statement(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record_statement)
    try:
        report = run_kline_storage_preflight(engine, minute_query_p99_ms=100.0, now=NOW)
    finally:
        event.remove(engine, "before_cursor_execute", record_statement)
        engine.dispose()

    payload = report.to_dict()
    assert report.status is KlineStorageStatus.UNSUPPORTED_FOR_PARTITIONING
    assert payload["evidence"]["dialect"] == "sqlite"
    assert payload["evidence"]["row_count"] == 3
    assert payload["evidence"]["partitioning"]["supported"] is False
    assert payload["evidence"]["minute_query"]["plans"] == []
    assert "12345.6789" not in report.to_json()
    assert "22345.6789" not in report.to_json()
    assert statements
    _assert_only_read_only_statements([(statement, {}) for statement in statements])
    assert all("pg_" not in statement.casefold() for statement in statements)


def test_cli_success_writes_explicit_report_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    engine = FakePostgresEngine()
    monkeypatch.setattr(kline_storage_cli, "create_engine", lambda database_url: engine)
    report_path = tmp_path / "kline-storage.json"
    environment = {
        "DATABASE_URL": f"postgresql://user:{DATABASE_PASSWORD}@db.example.com/app",
        "TUSHARE_TOKEN": PROVIDER_TOKEN,
    }

    exit_code = kline_storage_cli.main(
        [
            "--report-path",
            str(report_path),
            "--minute-query-p99-ms",
            "499.9",
        ],
        environ=environment,
    )

    captured = capsys.readouterr()
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == kline_storage_cli.EXIT_SUCCESS
    assert captured.err == ""
    assert json.loads(captured.out) == written
    assert written["status"] == "not_required"
    assert engine.disposed is True
    for secret in (DATABASE_PASSWORD, PROVIDER_TOKEN, str(SQL_PARAMETER_VALUE)):
        assert secret not in captured.out
        assert secret not in report_path.read_text(encoding="utf-8")


def test_cli_recommended_or_failed_gate_returns_one(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    recommended_engine = FakePostgresEngine()
    monkeypatch.setattr(
        kline_storage_cli,
        "create_engine",
        lambda database_url: recommended_engine,
    )
    recommended_path = tmp_path / "recommended.json"

    recommended_exit = kline_storage_cli.main(
        [
            "--database-url",
            f"postgresql://user:{DATABASE_PASSWORD}@db.example.com/app",
            "--minute-query-p99-ms",
            "500",
            "--report-path",
            str(recommended_path),
        ],
        environ={"TUSHARE_TOKEN": PROVIDER_TOKEN},
    )
    capsys.readouterr()

    failed_engine = FakePostgresEngine(fail_marker="kline_storage:period_stats")
    monkeypatch.setattr(
        kline_storage_cli,
        "create_engine",
        lambda database_url: failed_engine,
    )
    failed_path = tmp_path / "failed.json"
    failed_exit = kline_storage_cli.main(
        [
            "--database-url",
            f"postgresql://user:{DATABASE_PASSWORD}@db.example.com/app",
            "--minute-query-p99-ms",
            "100",
            "--report-path",
            str(failed_path),
        ],
        environ={"TUSHARE_TOKEN": PROVIDER_TOKEN},
    )

    captured = capsys.readouterr()
    assert recommended_exit == kline_storage_cli.EXIT_GATE_FAILED
    assert json.loads(recommended_path.read_text(encoding="utf-8"))["status"] == "recommended"
    assert failed_exit == kline_storage_cli.EXIT_GATE_FAILED
    assert json.loads(failed_path.read_text(encoding="utf-8"))["status"] == "failed"
    assert DATABASE_PASSWORD not in captured.out + captured.err
    assert PROVIDER_TOKEN not in captured.out + captured.err


def test_cli_report_failure_returns_two_without_leaking_inputs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    engine = FakePostgresEngine()
    monkeypatch.setattr(kline_storage_cli, "create_engine", lambda database_url: engine)
    report_path = tmp_path / PROVIDER_TOKEN / "missing" / "report.json"

    exit_code = kline_storage_cli.main(
        [
            "--database-url",
            f"postgresql://user:{DATABASE_PASSWORD}@db.example.com/app",
            "--minute-query-p99-ms",
            "100",
            "--report-path",
            str(report_path),
        ],
        environ={"TUSHARE_TOKEN": PROVIDER_TOKEN},
    )

    captured = capsys.readouterr()
    assert exit_code == kline_storage_cli.EXIT_REPORT_WRITE_FAILED
    assert captured.out == ""
    assert json.loads(captured.err)["status"] == "report_write_failed"
    assert DATABASE_PASSWORD not in captured.err
    assert PROVIDER_TOKEN not in captured.err


def _assert_only_read_only_statements(statements: list[tuple[str, dict[str, Any]]]) -> None:
    forbidden_tokens = (
        " ANALYZE",
        " INSERT ",
        " UPDATE ",
        " DELETE ",
        " CREATE ",
        " ALTER ",
        " DROP ",
        " TRUNCATE ",
        " LOCK ",
    )
    for statement, _parameters in statements:
        normalized = f" {statement.upper()} "
        assert not any(token in normalized for token in forbidden_tokens), statement
