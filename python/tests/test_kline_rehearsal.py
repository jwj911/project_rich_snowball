"""Focused fake tests for isolated K-line copy rehearsals."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import rehearse_kline_partition as rehearsal_cli
from services.kline_rehearsal import (
    KlineRehearsalCheckCode,
    KlineRehearsalCheckStatus,
    KlineRehearsalStatus,
    run_kline_copy_rehearsal,
)

SOURCE_TABLE = "kline_data"
SHADOW_TABLE = "kline_data_shadow_rehearsal"
NOW = datetime(2026, 8, 2, 12, 0, tzinfo=UTC)
MONTH_START = datetime(2026, 8, 1, tzinfo=UTC)
MIN_TIME = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)
MAX_TIME = datetime(2026, 8, 1, 9, 2, tzinfo=UTC)


class FakeMappingResult:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def one(self) -> dict[str, Any]:
        assert len(self.rows) == 1
        return self.rows[0]

    def one_or_none(self) -> dict[str, Any] | None:
        assert len(self.rows) <= 1
        return self.rows[0] if self.rows else None

    def all(self) -> list[dict[str, Any]]:
        return self.rows


class FakeScalarResult:
    def __init__(self, values: list[Any]):
        self.values = values

    def all(self) -> list[Any]:
        return self.values


class FakeResult:
    def __init__(
        self,
        *,
        rows: list[Any] | None = None,
        mappings: list[dict[str, Any]] | None = None,
        scalar: Any = None,
        scalars: list[Any] | None = None,
        rowcount: int = 0,
    ):
        self._rows = rows or []
        self._mappings = mappings or []
        self._scalar = scalar
        self._scalars = scalars or []
        self.rowcount = rowcount

    def mappings(self) -> FakeMappingResult:
        return FakeMappingResult(self._mappings)

    def scalar_one(self) -> Any:
        return self._scalar

    def scalars(self) -> FakeScalarResult:
        return FakeScalarResult(self._scalars)

    def all(self) -> list[Any]:
        return self._rows


class FakeSavepoint:
    def __init__(self):
        self.rolled_back = False

    def rollback(self) -> None:
        self.rolled_back = True


class FakeRehearsalConnection:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(
        self,
        *,
        shadow_row_count: int = 3,
        fail_marker: str | None = None,
    ):
        self.shadow_row_count = shadow_row_count
        self.fail_marker = fail_marker
        self.statements: list[str] = []
        self.driver_statements: list[str] = []
        self.savepoints: list[FakeSavepoint] = []

    def execute(self, statement, parameters=None) -> FakeResult:
        rendered = str(statement)
        self.statements.append(rendered)
        if self.fail_marker and self.fail_marker in rendered:
            raise RuntimeError("postgresql://admin:secret@localhost/private OHLCV=classified")

        if "kline_rehearsal:source_exists" in rendered:
            return FakeResult(scalar=True)
        if "kline_rehearsal:shadow_namespace" in rendered:
            return FakeResult(scalar=0)
        if "kline_rehearsal:source_summary" in rendered:
            return FakeResult(mappings=[_summary(3)])
        if "kline_rehearsal:shadow_summary" in rendered:
            return FakeResult(mappings=[_summary(self.shadow_row_count)])
        if "kline_rehearsal:source_period_counts" in rendered:
            return FakeResult(mappings=[{"period": "1m", "row_count": 3}])
        if "kline_rehearsal:shadow_period_counts" in rendered:
            return FakeResult(mappings=[{"period": "1m", "row_count": self.shadow_row_count}])
        if "kline_rehearsal:source_duplicates" in rendered:
            return FakeResult(scalar=0)
        if "kline_rehearsal:shadow_duplicates" in rendered:
            return FakeResult(scalar=0)
        if "kline_rehearsal:source_minute_months" in rendered:
            return FakeResult(scalars=[MONTH_START])
        if "kline_rehearsal:copy" in rendered:
            return FakeResult(rowcount=3)
        if "kline_rehearsal:sequence_set" in rendered:
            return FakeResult(scalar=4)
        if "kline_rehearsal:sequence_next" in rendered:
            return FakeResult(scalar=4)
        if "kline_rehearsal:foreign_keys" in rendered:
            return FakeResult(
                mappings=[
                    {
                        "variety_cascade_count": 1,
                        "contract_cascade_count": 1,
                    }
                ]
            )
        if "kline_rehearsal:core_query_scope" in rendered:
            return FakeResult(
                mappings=[
                    {
                        "variety_id": 11,
                        "contract_id": 22,
                        "period": "1m",
                        "start_time": MIN_TIME,
                        "end_time": MAX_TIME,
                        "row_count": 3,
                    }
                ]
            )
        if "kline_rehearsal:source_core_query" in rendered:
            return FakeResult(rows=_query_rows())
        if "kline_rehearsal:shadow_core_query" in rendered:
            return FakeResult(rows=_query_rows())
        if "kline_rehearsal:conflict_do_nothing" in rendered:
            return FakeResult(rowcount=0)
        if "kline_rehearsal:cascade_variety" in rendered:
            return FakeResult(scalar=901)
        if "kline_rehearsal:cascade_contract" in rendered:
            return FakeResult(scalar=902)
        if "kline_rehearsal:cascade_shadow_row" in rendered:
            return FakeResult(rowcount=1)
        if "kline_rehearsal:cascade_before" in rendered:
            return FakeResult(scalar=1)
        if "kline_rehearsal:cascade_delete" in rendered:
            return FakeResult(rowcount=1)
        if "kline_rehearsal:cascade_after" in rendered:
            return FakeResult(scalar=0)
        if "kline_rehearsal:partition_pruning" in rendered:
            return FakeResult(
                scalar=[
                    {
                        "Plan": {
                            "Node Type": "Index Scan",
                            "Relation Name": (f"{SHADOW_TABLE}_minute_202608"),
                        }
                    }
                ]
            )
        return FakeResult()

    def exec_driver_sql(self, statement: str) -> None:
        self.driver_statements.append(statement)

    def begin_nested(self) -> FakeSavepoint:
        savepoint = FakeSavepoint()
        self.savepoints.append(savepoint)
        return savepoint


class FakeTransaction:
    def __init__(self, engine: FakeRehearsalEngine):
        self.engine = engine

    def __enter__(self) -> FakeRehearsalConnection:
        self.engine.transaction_entered = True
        return self.engine.connection

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.engine.rolled_back = exc_type is not None
        self.engine.committed = exc_type is None
        return None


class FakeRehearsalEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, connection: FakeRehearsalConnection):
        self.connection = connection
        self.transaction_entered = False
        self.rolled_back = False
        self.committed = False
        self.disposed = False

    def begin(self) -> FakeTransaction:
        return FakeTransaction(self)

    def dispose(self) -> None:
        self.disposed = True


def _summary(row_count: int) -> dict[str, Any]:
    return {
        "row_count": row_count,
        "min_trading_time": MIN_TIME,
        "max_trading_time": MAX_TIME,
        "max_id": 3,
    }


def _query_rows() -> list[tuple[int, datetime]]:
    return [
        (3, MAX_TIME),
        (2, datetime(2026, 8, 1, 9, 1, tzinfo=UTC)),
        (1, MIN_TIME),
    ]


def _check_map(report) -> dict[str, dict[str, Any]]:
    return {check.code.value: check.to_dict() for check in report.checks}


def test_consistent_copy_passes_all_checks_and_explicitly_cleans_resources():
    connection = FakeRehearsalConnection()
    engine = FakeRehearsalEngine(connection)

    report = run_kline_copy_rehearsal(
        engine,
        SOURCE_TABLE,
        SHADOW_TABLE,
        cleanup_on_success=True,
        trace_id="trace-consistent",
        now=NOW,
    )

    checks = _check_map(report)
    assert report.status is KlineRehearsalStatus.PASSED
    assert report.passed is True
    assert engine.committed is True
    assert engine.rolled_back is False
    assert connection.savepoints[0].rolled_back is True
    assert connection.driver_statements[0] == ("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
    assert any(
        f'CREATE TABLE IF NOT EXISTS "{SHADOW_TABLE}_minute_202608"' in statement
        for statement in connection.driver_statements
    )
    assert checks[KlineRehearsalCheckCode.COPY_COUNT.value]["evidence"] == {
        "source": 3,
        "shadow": 3,
        "source_minute_month_count": 1,
    }
    assert checks[KlineRehearsalCheckCode.PARTITION_PRUNING.value]["evidence"]["relation_names"] == [
        f"{SHADOW_TABLE}_minute_202608"
    ]
    assert checks[KlineRehearsalCheckCode.CLEANUP.value]["evidence"] == {"performed": True}
    assert any(
        statement == f'DROP TABLE IF EXISTS "{SHADOW_TABLE}" CASCADE' for statement in connection.driver_statements
    )
    assert any(
        statement == f'DROP SEQUENCE IF EXISTS "{SHADOW_TABLE}_id_seq"' for statement in connection.driver_statements
    )
    assert not any("RENAME" in statement.upper() for statement in connection.driver_statements)


def test_copy_count_mismatch_fails_with_aggregate_report_and_rolls_back():
    connection = FakeRehearsalConnection(shadow_row_count=2)
    engine = FakeRehearsalEngine(connection)

    report = run_kline_copy_rehearsal(
        engine,
        SOURCE_TABLE,
        SHADOW_TABLE,
        trace_id="trace-mismatch",
        now=NOW,
    )

    checks = _check_map(report)
    assert report.status is KlineRehearsalStatus.FAILED
    assert report.error_code == KlineRehearsalCheckCode.COPY_COUNT.value
    assert report.error_type == "KlineRehearsalValidationError"
    assert engine.rolled_back is True
    assert engine.committed is False
    assert checks[KlineRehearsalCheckCode.COPY_COUNT.value]["status"] == (KlineRehearsalCheckStatus.FAILED.value)
    assert checks[KlineRehearsalCheckCode.TRANSACTION_ROLLBACK.value]["evidence"] == {"rolled_back": True}
    assert not any(statement.startswith("DROP TABLE") for statement in connection.driver_statements)


def test_database_failure_report_redacts_message_and_rolls_back_created_resources():
    connection = FakeRehearsalConnection(fail_marker="kline_rehearsal:shadow_summary")
    engine = FakeRehearsalEngine(connection)

    report = run_kline_copy_rehearsal(
        engine,
        SOURCE_TABLE,
        SHADOW_TABLE,
        trace_id="trace-failure",
        now=NOW,
    )
    payload = report.to_json()

    assert report.status is KlineRehearsalStatus.FAILED
    assert report.error_code == KlineRehearsalCheckCode.EXECUTION.value
    assert report.error_type == "RuntimeError"
    assert engine.rolled_back is True
    assert '"rolled_back":true' in payload
    assert "admin" not in payload
    assert "secret" not in payload
    assert "classified" not in payload
    assert "OHLCV" not in payload
    assert "open_price" not in payload


def test_dry_run_report_is_stable_and_does_not_open_database(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(
        rehearsal_cli,
        "create_engine",
        lambda *args, **kwargs: pytest.fail("dry-run opened a database"),
    )
    monkeypatch.setattr(rehearsal_cli.uuid, "uuid4", lambda: SimpleNamespace(hex="trace-dry-run"))

    exit_code = rehearsal_cli.main(
        [
            "--source-table",
            SOURCE_TABLE,
            "--shadow-table",
            SHADOW_TABLE,
            "--cleanup",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == rehearsal_cli.EXIT_SUCCESS
    assert captured.err == ""
    assert payload["trace_id"] == "trace-dry-run"
    assert payload["status"] == "dry_run"
    assert payload["cleanup_on_success"] is True
    assert payload["summary"]["status_counts"] == {"planned": 14}


def test_cli_apply_runs_rehearsal_and_disposes_engine(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    engine = FakeRehearsalEngine(FakeRehearsalConnection())
    monkeypatch.setattr(rehearsal_cli, "create_engine", lambda *args, **kwargs: engine)

    exit_code = rehearsal_cli.main(
        [
            "--source-table",
            SOURCE_TABLE,
            "--shadow-table",
            SHADOW_TABLE,
            "--apply",
            "--confirm",
            "--cleanup",
            "--database-url",
            "postgresql://user:pass@localhost/app",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == rehearsal_cli.EXIT_SUCCESS
    assert captured.err == ""
    assert payload["status"] == "passed"
    assert payload["cleanup_on_success"] is True
    assert engine.disposed is True


@pytest.mark.parametrize(
    ("arguments", "environment", "error_code"),
    [
        (
            [
                "--source-table",
                "other_table",
                "--shadow-table",
                SHADOW_TABLE,
                "--apply",
                "--confirm",
            ],
            {"DATABASE_URL": "postgresql://user:pass@localhost/app"},
            KlineRehearsalCheckCode.SOURCE_TABLE.value,
        ),
        (
            [
                "--source-table",
                SOURCE_TABLE,
                "--shadow-table",
                "kline_data",
                "--apply",
                "--confirm",
            ],
            {"DATABASE_URL": "postgresql://user:pass@localhost/app"},
            KlineRehearsalCheckCode.SHADOW_NAMESPACE.value,
        ),
        (
            [
                "--source-table",
                SOURCE_TABLE,
                "--shadow-table",
                SHADOW_TABLE,
                "--apply",
            ],
            {"DATABASE_URL": "postgresql://user:pass@localhost/app"},
            "KLINE_REHEARSAL_CONFIRMATION_REQUIRED",
        ),
        (
            [
                "--source-table",
                SOURCE_TABLE,
                "--shadow-table",
                SHADOW_TABLE,
                "--apply",
                "--confirm",
                "--database-url",
                "sqlite:///app.db",
            ],
            {},
            "KLINE_REHEARSAL_POSTGRESQL_REQUIRED",
        ),
    ],
)
def test_cli_refusals_emit_trace_json_without_opening_database(
    arguments: list[str],
    environment: dict[str, str],
    error_code: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(
        rehearsal_cli,
        "create_engine",
        lambda *args, **kwargs: pytest.fail("refused operation opened a database"),
    )

    exit_code = rehearsal_cli.main(arguments, environ=environment)

    captured = capsys.readouterr()
    payload = json.loads(captured.err)
    assert exit_code == rehearsal_cli.EXIT_REFUSED
    assert captured.out == ""
    assert payload["status"] == "failed"
    assert payload["trace_id"]
    assert payload["error"]["code"] == error_code
    assert "pass" not in captured.err
