"""Focused tests for K-line shadow partition planning and management."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from scripts import manage_kline_partitions as partition_cli
from services.kline_partitioning import (
    KLINE_LONG_PERIOD_ALIASES,
    KLINE_MINUTE_PERIOD_ALIASES,
    ActiveKlineTableRejectedError,
    InvalidShadowTableError,
    UnsafeShadowTableError,
    UnsupportedPartitionDialectError,
    apply_kline_partition_plan,
    build_kline_partition_plan,
)

NOW = datetime(2026, 12, 31, 23, 30, tzinfo=UTC)
SHADOW_TABLE = "kline_data_shadow"


class IdempotentFakeConnection:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self):
        self.objects: set[str] = set()
        self.statements: list[str] = []
        self.overwrites = 0

    def exec_driver_sql(self, statement: str) -> None:
        self.statements.append(statement)
        match = re.match(
            r'CREATE (?:SEQUENCE|TABLE|INDEX) IF NOT EXISTS "([^"]+)"',
            statement,
        )
        if match is None:
            self.overwrites += 1
            raise AssertionError(f"non-idempotent DDL: {statement}")
        self.objects.add(match.group(1))


class FakeEngine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self):
        self.connection = IdempotentFakeConnection()
        self.disposed = False

    def begin(self) -> FakeEngine:
        return self

    def __enter__(self) -> IdempotentFakeConnection:
        return self.connection

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def dispose(self) -> None:
        self.disposed = True


def test_period_alias_constants_are_complete_and_disjoint():
    assert KLINE_MINUTE_PERIOD_ALIASES == (
        "1m",
        "1",
        "5m",
        "5",
        "15m",
        "15",
        "30m",
        "30",
        "1h",
        "60",
    )
    assert KLINE_LONG_PERIOD_ALIASES == ("1d", "D", "1w", "W", "M")
    assert set(KLINE_MINUTE_PERIOD_ALIASES).isdisjoint(KLINE_LONG_PERIOD_ALIASES)


def test_parent_ddl_matches_current_kline_model_and_partition_constraints():
    plan = build_kline_partition_plan(SHADOW_TABLE, now=NOW)
    sql = plan.to_sql()
    parent = plan.statements[1]

    expected_columns = (
        '"id" INTEGER NOT NULL DEFAULT nextval(\'"kline_data_shadow_id_seq"\'::regclass)',
        '"variety_id" INTEGER NOT NULL',
        '"contract_id" INTEGER NOT NULL',
        '"period" VARCHAR(10) NOT NULL',
        '"trading_time" TIMESTAMP WITH TIME ZONE NOT NULL',
        '"trading_date" DATE',
        '"open_price" NUMERIC(19, 4) NOT NULL',
        '"high_price" NUMERIC(19, 4) NOT NULL',
        '"low_price" NUMERIC(19, 4) NOT NULL',
        '"close_price" NUMERIC(19, 4) NOT NULL',
        '"volume" INTEGER NOT NULL',
        '"open_interest" INTEGER',
        '"created_at" TIMESTAMP WITH TIME ZONE',
    )
    for column in expected_columns:
        assert column in parent

    assert 'PRIMARY KEY ("id", "period", "trading_time")' in parent
    assert 'UNIQUE ("variety_id", "contract_id", "period", "trading_time")' in parent
    assert 'REFERENCES "varieties" ("id") ON DELETE CASCADE' in parent
    assert 'REFERENCES "fut_contracts" ("id") ON DELETE CASCADE' in parent
    assert ') PARTITION BY LIST ("period")' in parent
    assert sql.startswith('CREATE SEQUENCE IF NOT EXISTS "kline_data_shadow_id_seq" AS INTEGER;')
    assert "BIGSERIAL" not in sql
    assert "SERIAL" not in sql


def test_alias_routing_default_partition_and_query_indexes_are_explicit():
    plan = build_kline_partition_plan(SHADOW_TABLE, now=NOW)
    minute = plan.statements[2]
    long_term = plan.statements[3]
    default = plan.statements[4]
    sql = plan.to_sql()

    assert minute.endswith("PARTITION BY RANGE (trading_time)")
    for alias in KLINE_MINUTE_PERIOD_ALIASES:
        assert f"'{alias}'" in minute

    assert "PARTITION BY" not in long_term
    for alias in KLINE_LONG_PERIOD_ALIASES:
        assert f"'{alias}'" in long_term

    assert default == (
        'CREATE TABLE IF NOT EXISTS "kline_data_shadow_default" PARTITION OF "kline_data_shadow" DEFAULT'
    )
    assert 'ON "kline_data_shadow" ("variety_id", "period", "trading_time")' in sql
    assert 'ON "kline_data_shadow" ("contract_id", "period", "trading_time")' in sql
    assert 'ON "kline_data_shadow" ("contract_id")' in sql
    assert 'ON "kline_data_shadow" ("trading_date")' in sql

    forbidden = (
        " INSERT INTO ",
        " SELECT ",
        " UPDATE ",
        " DELETE FROM ",
        " DROP ",
        " ALTER ",
    )
    normalized = f" {sql.upper()} "
    assert not any(token in normalized for token in forbidden)


def test_future_three_months_cross_year_with_exact_half_open_boundaries():
    plan = build_kline_partition_plan(SHADOW_TABLE, now=NOW)

    assert [(partition.table_name, partition.start, partition.end) for partition in plan.month_partitions] == [
        (
            "kline_data_shadow_minute_202701",
            datetime(2027, 1, 1, tzinfo=UTC),
            datetime(2027, 2, 1, tzinfo=UTC),
        ),
        (
            "kline_data_shadow_minute_202702",
            datetime(2027, 2, 1, tzinfo=UTC),
            datetime(2027, 3, 1, tzinfo=UTC),
        ),
        (
            "kline_data_shadow_minute_202703",
            datetime(2027, 3, 1, tzinfo=UTC),
            datetime(2027, 4, 1, tzinfo=UTC),
        ),
    ]
    assert (
        "FOR VALUES FROM (TIMESTAMPTZ '2027-02-01 00:00:00+00') "
        "TO (TIMESTAMPTZ '2027-03-01 00:00:00+00')" in plan.to_sql()
    )


def test_same_inputs_produce_stable_plan_and_sql():
    first = build_kline_partition_plan(SHADOW_TABLE, now=date(2026, 8, 31))
    second = build_kline_partition_plan(SHADOW_TABLE, now=date(2026, 8, 1))

    assert first == second
    assert first.to_sql() == second.to_sql()
    assert first.to_sql().endswith(";")


@pytest.mark.parametrize(
    ("table_name", "error_type"),
    [
        ("kline_data", ActiveKlineTableRejectedError),
        ("kline_data_next", UnsafeShadowTableError),
        ("kline-data-shadow", InvalidShadowTableError),
        ("public.kline_data_shadow", InvalidShadowTableError),
        ("kline_data_shadow;DROP_TABLE", InvalidShadowTableError),
        ("9_kline_shadow", InvalidShadowTableError),
        ("kline_data_shadow_" + "x" * 64, InvalidShadowTableError),
    ],
)
def test_unsafe_or_invalid_targets_are_hard_rejected(
    table_name: str,
    error_type: type[Exception],
):
    with pytest.raises(error_type):
        build_kline_partition_plan(table_name, now=NOW)


def test_apply_is_postgres_only_and_repeated_apply_does_not_overwrite():
    plan = build_kline_partition_plan(SHADOW_TABLE, now=NOW)
    connection = IdempotentFakeConnection()

    first_count = apply_kline_partition_plan(connection, plan)
    first_objects = connection.objects.copy()
    second_count = apply_kline_partition_plan(connection, plan)

    assert first_count == second_count == len(plan.statements)
    assert connection.objects == first_objects
    assert connection.overwrites == 0
    assert len(connection.statements) == len(plan.statements) * 2
    assert all("IF NOT EXISTS" in statement for statement in connection.statements)

    sqlite_connection = SimpleNamespace(
        dialect=SimpleNamespace(name="sqlite"),
        exec_driver_sql=lambda statement: pytest.fail(statement),
    )
    with pytest.raises(UnsupportedPartitionDialectError):
        apply_kline_partition_plan(sqlite_connection, plan)


def test_cli_defaults_to_stable_dry_run_without_opening_a_database(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    def fixed_builder(shadow_table: str):
        return build_kline_partition_plan(shadow_table, now=NOW)

    monkeypatch.setattr(partition_cli, "build_kline_partition_plan", fixed_builder)
    monkeypatch.setattr(
        partition_cli,
        "create_engine",
        lambda *args, **kwargs: pytest.fail("dry-run opened a database"),
    )

    first_exit = partition_cli.main(["--shadow-table", SHADOW_TABLE], environ={})
    first_output = capsys.readouterr()
    second_exit = partition_cli.main(["--shadow-table", SHADOW_TABLE], environ={})
    second_output = capsys.readouterr()

    assert first_exit == second_exit == partition_cli.EXIT_SUCCESS
    assert first_output.out == second_output.out
    assert first_output.err == second_output.err == ""
    assert 'CREATE TABLE IF NOT EXISTS "kline_data_shadow"' in first_output.out
    assert "INSERT INTO" not in first_output.out


@pytest.mark.parametrize(
    ("arguments", "environment", "code"),
    [
        (
            ["--shadow-table", SHADOW_TABLE, "--apply"],
            {"DATABASE_URL": "postgresql://user:pass@localhost/app"},
            "confirmation_required",
        ),
        (
            ["--shadow-table", SHADOW_TABLE, "--apply", "--confirm"],
            {},
            "database_url_required",
        ),
        (
            [
                "--shadow-table",
                SHADOW_TABLE,
                "--apply",
                "--confirm",
                "--database-url",
                "sqlite:///app.db",
            ],
            {},
            "postgresql_required",
        ),
        (
            ["--shadow-table", "kline_data", "--apply", "--confirm"],
            {"DATABASE_URL": "postgresql://user:pass@localhost/app"},
            "unsafe_shadow_table",
        ),
    ],
)
def test_cli_hard_refusals_do_not_open_a_database(
    arguments: list[str],
    environment: dict[str, str],
    code: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(
        partition_cli,
        "create_engine",
        lambda *args, **kwargs: pytest.fail("refused operation opened a database"),
    )

    exit_code = partition_cli.main(arguments, environ=environment)

    captured = capsys.readouterr()
    assert exit_code == partition_cli.EXIT_REFUSED
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["code"] == code


def test_cli_apply_requires_all_gates_and_uses_one_transaction(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    engine = FakeEngine()
    monkeypatch.setattr(partition_cli, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(
        partition_cli,
        "build_kline_partition_plan",
        lambda shadow_table: build_kline_partition_plan(shadow_table, now=NOW),
    )

    exit_code = partition_cli.main(
        [
            "--shadow-table",
            SHADOW_TABLE,
            "--apply",
            "--confirm",
            "--database-url",
            "postgresql://user:pass@localhost/app",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    payload: dict[str, Any] = json.loads(captured.out)
    assert exit_code == partition_cli.EXIT_SUCCESS
    assert captured.err == ""
    assert payload == {
        "shadow_table": SHADOW_TABLE,
        "statement_count": len(engine.connection.statements),
        "status": "applied",
    }
    assert engine.disposed is True


def test_cli_rechecks_actual_engine_dialect_before_apply(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    engine = FakeEngine()
    engine.dialect = SimpleNamespace(name="sqlite")
    monkeypatch.setattr(partition_cli, "create_engine", lambda *args, **kwargs: engine)

    exit_code = partition_cli.main(
        [
            "--shadow-table",
            SHADOW_TABLE,
            "--apply",
            "--confirm",
            "--database-url",
            "postgresql://user:pass@localhost/app",
        ],
        environ={},
    )

    captured = capsys.readouterr()
    assert exit_code == partition_cli.EXIT_REFUSED
    assert captured.out == ""
    assert json.loads(captured.err)["error"]["code"] == "postgresql_required"
    assert engine.connection.statements == []
    assert engine.disposed is True


def test_cli_missing_shadow_table_is_a_parser_error():
    with pytest.raises(SystemExit) as exc_info:
        partition_cli.main([], environ={})

    assert exc_info.value.code == 2
