"""PostgreSQL integration coverage for the R8 K-line shadow lifecycle."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from models import FutContractDB, KlineDataDB, VarietyDB
from services import kline_rehearsal
from services.kline_partitioning import (
    KLINE_LONG_PERIOD_ALIASES,
    KLINE_MINUTE_PERIOD_ALIASES,
    apply_kline_partition_plan,
    build_kline_partition_plan,
    build_kline_source_month_partition_statements,
)
from services.kline_rehearsal import (
    KlineRehearsalCheckCode,
    KlineRehearsalStatus,
    run_kline_copy_rehearsal,
)

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
    reason="R8 K-line partition integration requires PostgreSQL DATABASE_URL",
)

SOURCE_TABLE = "kline_data"
MINUTE_TIME = datetime(2098, 8, 15, 9, 30, tzinfo=UTC)
LONG_TIME = datetime(2098, 8, 15, tzinfo=UTC)
UNKNOWN_PERIOD = "4h"
COPY_COLUMNS = (
    "id",
    "variety_id",
    "contract_id",
    "period",
    "trading_time",
    "trading_date",
    "open_price",
    "high_price",
    "low_price",
    "close_price",
    "volume",
    "open_interest",
    "created_at",
)


@pytest.fixture(scope="module")
def pg_partition_sample():
    """Create unique source rows and guarantee cleanup of every R8 test object."""
    assert _pg_engine is not None
    assert _PgSessionLocal is not None

    suffix = uuid.uuid4().hex[:6]
    symbol = f"R8PG{suffix}".upper()
    contract_code = f"{symbol}01"
    ts_code = f"{contract_code}.TST"
    assert len(symbol) <= FutContractDB.__table__.c.fut_code.type.length
    shadow_tables = {
        "routes": f"kline_data_shadow_routes_{suffix}",
        "rehearsal": f"kline_data_shadow_rehearsal_{suffix}",
        "failure": f"kline_data_shadow_failure_{suffix}",
    }

    session = _PgSessionLocal()
    variety = VarietyDB(
        symbol=symbol,
        contract_code=contract_code,
        name="R8 PostgreSQL partition integration",
        exchange="TEST",
        category="test",
        is_active=False,
    )
    contract = FutContractDB(
        ts_code=ts_code,
        symbol=contract_code,
        name="R8 PostgreSQL partition integration",
        fut_code=symbol,
        exchange="TEST",
        is_active=False,
    )
    session.add_all([variety, contract])
    session.flush()

    for period in KLINE_MINUTE_PERIOD_ALIASES:
        session.add(_kline_row(variety.id, contract.id, period, MINUTE_TIME))
    for period in (*KLINE_LONG_PERIOD_ALIASES, UNKNOWN_PERIOD):
        session.add(_kline_row(variety.id, contract.id, period, LONG_TIME))
    session.commit()
    variety_id = variety.id
    contract_id = contract.id
    session.close()

    try:
        yield {
            "variety_id": variety_id,
            "contract_id": contract_id,
            "shadow_tables": shadow_tables,
        }
    finally:
        with _pg_engine.begin() as connection:
            for shadow_table in shadow_tables.values():
                plan = build_kline_partition_plan(shadow_table, now=MINUTE_TIME)
                connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{plan.shadow_table}" CASCADE')
                connection.exec_driver_sql(f'DROP SEQUENCE IF EXISTS "{plan.sequence_name}"')
            connection.execute(
                text("DELETE FROM kline_data WHERE variety_id = :variety_id"),
                {"variety_id": variety_id},
            )
            connection.execute(
                text("DELETE FROM fut_contracts WHERE id = :contract_id"),
                {"contract_id": contract_id},
            )
            connection.execute(
                text("DELETE FROM varieties WHERE id = :variety_id"),
                {"variety_id": variety_id},
            )


def _kline_row(
    variety_id: int,
    contract_id: int,
    period: str,
    trading_time: datetime,
) -> KlineDataDB:
    return KlineDataDB(
        variety_id=variety_id,
        contract_id=contract_id,
        period=period,
        trading_time=trading_time,
        trading_date=trading_time.date(),
        open_price=100,
        high_price=102,
        low_price=99,
        close_price=101,
        volume=10,
        open_interest=20,
    )


def _drop_shadow(connection, shadow_table: str) -> None:
    plan = build_kline_partition_plan(shadow_table, now=MINUTE_TIME)
    connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{plan.shadow_table}" CASCADE')
    connection.exec_driver_sql(f'DROP SEQUENCE IF EXISTS "{plan.sequence_name}"')


def _assert_shadow_absent(shadow_table: str) -> None:
    assert _pg_engine is not None
    plan = build_kline_partition_plan(shadow_table, now=MINUTE_TIME)
    with _pg_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT to_regclass(:table_name)"),
                {"table_name": plan.shadow_table},
            ).scalar_one()
            is None
        )
        assert (
            connection.execute(
                text("SELECT to_regclass(:sequence_name)"),
                {"sequence_name": plan.sequence_name},
            ).scalar_one()
            is None
        )


def test_postgres_routes_all_aliases_and_default_partition_idempotently(
    pg_partition_sample,
):
    assert _pg_engine is not None
    variety_id = pg_partition_sample["variety_id"]
    shadow_table = pg_partition_sample["shadow_tables"]["routes"]
    plan = build_kline_partition_plan(shadow_table, now=MINUTE_TIME)
    columns = ", ".join(f'"{column}"' for column in COPY_COLUMNS)

    with _pg_engine.begin() as connection:
        try:
            first_count = apply_kline_partition_plan(connection, plan)
            second_count = apply_kline_partition_plan(connection, plan)
            for statement in build_kline_source_month_partition_statements(
                shadow_table,
                (MINUTE_TIME,),
            ):
                connection.exec_driver_sql(statement)

            connection.exec_driver_sql(
                f'INSERT INTO "{shadow_table}" ({columns}) '
                f"SELECT {columns} FROM kline_data WHERE variety_id = {int(variety_id)}"
            )
            routes = dict(
                connection.execute(
                    text(
                        f"SELECT period, tableoid::regclass::text AS relation_name "
                        f'FROM "{shadow_table}" WHERE variety_id = :variety_id'
                    ),
                    {"variety_id": variety_id},
                ).all()
            )

            assert first_count == second_count == len(plan.statements)
            minute_partition = f"{shadow_table}_minute_209808"
            for period in KLINE_MINUTE_PERIOD_ALIASES:
                assert routes[period] == minute_partition
            for period in KLINE_LONG_PERIOD_ALIASES:
                assert routes[period] == f"{shadow_table}_long"
            assert routes[UNKNOWN_PERIOD] == f"{shadow_table}_default"
        finally:
            _drop_shadow(connection, shadow_table)

    _assert_shadow_absent(shadow_table)


def test_postgres_rehearsal_validates_pruning_and_cleans_success(
    pg_partition_sample,
):
    assert _pg_engine is not None
    shadow_table = pg_partition_sample["shadow_tables"]["rehearsal"]

    report = run_kline_copy_rehearsal(
        _pg_engine,
        SOURCE_TABLE,
        shadow_table,
        cleanup_on_success=True,
        trace_id="r8-postgres-success",
        now=MINUTE_TIME,
    )

    check_codes = {check.code for check in report.checks}
    assert report.status is KlineRehearsalStatus.PASSED
    assert {
        KlineRehearsalCheckCode.COPY_COUNT,
        KlineRehearsalCheckCode.PERIOD_COUNTS,
        KlineRehearsalCheckCode.TRADING_TIME_BOUNDS,
        KlineRehearsalCheckCode.NATURAL_KEY_DUPLICATES,
        KlineRehearsalCheckCode.SEQUENCE_NEXT_VALUE,
        KlineRehearsalCheckCode.FOREIGN_KEYS,
        KlineRehearsalCheckCode.CORE_QUERY,
        KlineRehearsalCheckCode.CONFLICT_DO_NOTHING,
        KlineRehearsalCheckCode.CASCADE_FOREIGN_KEY,
        KlineRehearsalCheckCode.PARTITION_PRUNING,
        KlineRehearsalCheckCode.CLEANUP,
    } <= check_codes
    _assert_shadow_absent(shadow_table)


def test_postgres_rehearsal_rolls_back_created_resources_on_failure(
    pg_partition_sample,
    monkeypatch: pytest.MonkeyPatch,
):
    assert _pg_engine is not None
    shadow_table = pg_partition_sample["shadow_tables"]["failure"]
    original_collector = kline_rehearsal._collect_aggregate_evidence

    def fail_after_copy(connection, table_name: str, role: str):
        if role == "shadow":
            raise RuntimeError("forced integration rollback")
        return original_collector(connection, table_name, role)

    monkeypatch.setattr(
        kline_rehearsal,
        "_collect_aggregate_evidence",
        fail_after_copy,
    )
    report = run_kline_copy_rehearsal(
        _pg_engine,
        SOURCE_TABLE,
        shadow_table,
        trace_id="r8-postgres-failure",
        now=MINUTE_TIME,
    )

    assert report.status is KlineRehearsalStatus.FAILED
    assert report.error_code == KlineRehearsalCheckCode.EXECUTION.value
    assert any(check.code is KlineRehearsalCheckCode.TRANSACTION_ROLLBACK for check in report.checks)
    _assert_shadow_absent(shadow_table)
