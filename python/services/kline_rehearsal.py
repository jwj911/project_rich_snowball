"""Isolated PostgreSQL rehearsal for copying K-line data into a shadow table."""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import column, delete, func, select, table, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection, Engine

from services.kline_partitioning import (
    KLINE_ACTIVE_TABLE,
    KLINE_MINUTE_PERIOD_ALIASES,
    KLINE_MONTH_PARTITION_FORMAT,
    KlinePartitionPlan,
    UnsupportedPartitionDialectError,
    apply_kline_partition_plan,
    build_kline_partition_plan,
    build_kline_source_month_partition_statements,
    validate_shadow_table_name,
)

KLINE_REHEARSAL_ADVISORY_LOCK_ID = 8_204_273_001
KLINE_REHEARSAL_QUERY_LIMIT = 1000
KLINE_COPY_COLUMNS = (
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
KLINE_NATURAL_KEY_COLUMNS = (
    "variety_id",
    "contract_id",
    "period",
    "trading_time",
)

_POSTGRES_DIALECT = postgresql.dialect()
_SAFE_ERROR_TYPE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")


class KlineRehearsalError(RuntimeError):
    """Base error for an unsafe or failed K-line rehearsal."""


class InvalidRehearsalSourceError(KlineRehearsalError, ValueError):
    """Raised when the explicit rehearsal source is not kline_data."""


class ExistingShadowResourceError(KlineRehearsalError):
    """Raised when the requested shadow namespace is not empty."""


class KlineRehearsalValidationError(KlineRehearsalError):
    """Raised when copied data or semantics do not match the source."""

    def __init__(self, code: KlineRehearsalCheckCode):
        super().__init__(code.value)
        self.code = code


class KlineRehearsalStatus(StrEnum):
    """Overall rehearsal result."""

    DRY_RUN = "dry_run"
    PASSED = "passed"
    FAILED = "failed"


class KlineRehearsalCheckStatus(StrEnum):
    """Status of one stable rehearsal check."""

    PLANNED = "planned"
    PASSED = "passed"
    FAILED = "failed"


class KlineRehearsalCheckCode(StrEnum):
    """Stable, non-sensitive rehearsal check codes."""

    SOURCE_TABLE = "KLINE_REHEARSAL_SOURCE_TABLE"
    SHADOW_NAMESPACE = "KLINE_REHEARSAL_SHADOW_NAMESPACE"
    ISOLATION_LOCK = "KLINE_REHEARSAL_ISOLATION_LOCK"
    COPY_COUNT = "KLINE_REHEARSAL_COPY_COUNT"
    PERIOD_COUNTS = "KLINE_REHEARSAL_PERIOD_COUNTS"
    TRADING_TIME_BOUNDS = "KLINE_REHEARSAL_TRADING_TIME_BOUNDS"
    NATURAL_KEY_DUPLICATES = "KLINE_REHEARSAL_NATURAL_KEY_DUPLICATES"
    SEQUENCE_NEXT_VALUE = "KLINE_REHEARSAL_SEQUENCE_NEXT_VALUE"
    FOREIGN_KEYS = "KLINE_REHEARSAL_FOREIGN_KEYS"
    CORE_QUERY = "KLINE_REHEARSAL_CORE_QUERY"
    CONFLICT_DO_NOTHING = "KLINE_REHEARSAL_CONFLICT_DO_NOTHING"
    CASCADE_FOREIGN_KEY = "KLINE_REHEARSAL_CASCADE_FOREIGN_KEY"
    PARTITION_PRUNING = "KLINE_REHEARSAL_PARTITION_PRUNING"
    CLEANUP = "KLINE_REHEARSAL_CLEANUP"
    TRANSACTION_ROLLBACK = "KLINE_REHEARSAL_TRANSACTION_ROLLBACK"
    EXECUTION = "KLINE_REHEARSAL_EXECUTION"


@dataclass(frozen=True)
class KlineRehearsalCheck:
    """One aggregate or metadata-only rehearsal check."""

    code: KlineRehearsalCheckCode
    status: KlineRehearsalCheckStatus
    evidence: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "status": self.status.value,
            "evidence": dict(self.evidence),
        }


@dataclass(frozen=True)
class KlineRehearsalReport:
    """Traceable report that excludes raw K-line values and database details."""

    trace_id: str
    generated_at: str
    status: KlineRehearsalStatus
    source_table: str
    shadow_table: str
    cleanup_on_success: bool
    checks: tuple[KlineRehearsalCheck, ...]
    error_code: str | None = None
    error_type: str | None = None
    schema_version: int = 1

    @property
    def passed(self) -> bool:
        return self.status is KlineRehearsalStatus.PASSED

    def to_dict(self) -> dict[str, Any]:
        status_counts = Counter(check.status.value for check in self.checks)
        return {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "generated_at": self.generated_at,
            "status": self.status.value,
            "source_table": self.source_table,
            "shadow_table": self.shadow_table,
            "cleanup_on_success": self.cleanup_on_success,
            "summary": {
                "check_total": len(self.checks),
                "status_counts": dict(sorted(status_counts.items())),
            },
            "checks": [check.to_dict() for check in self.checks],
            "error": (
                {
                    "code": self.error_code,
                    "error_type": self.error_type,
                }
                if self.error_code and self.error_type
                else None
            ),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )


@dataclass(frozen=True)
class _KlineAggregateEvidence:
    row_count: int
    period_counts: Mapping[str, int]
    min_trading_time: Any
    max_trading_time: Any
    max_id: int
    duplicate_count: int


def validate_rehearsal_source_table(source_table: str) -> str:
    """Require the active K-line table as an explicit, unqualified source."""
    if source_table != KLINE_ACTIVE_TABLE:
        raise InvalidRehearsalSourceError("Rehearsal source must be exactly kline_data.")
    return source_table


def build_kline_rehearsal_dry_run_report(
    source_table: str,
    shadow_table: str,
    *,
    cleanup_on_success: bool = False,
    trace_id: str | None = None,
    now: datetime | None = None,
) -> KlineRehearsalReport:
    """Describe the checks without opening a database or changing resources."""
    source = validate_rehearsal_source_table(source_table)
    shadow = validate_shadow_table_name(shadow_table)
    planned_codes = (
        KlineRehearsalCheckCode.SOURCE_TABLE,
        KlineRehearsalCheckCode.SHADOW_NAMESPACE,
        KlineRehearsalCheckCode.ISOLATION_LOCK,
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
    )
    return KlineRehearsalReport(
        trace_id=trace_id or uuid.uuid4().hex,
        generated_at=_format_time(now or datetime.now(UTC)),
        status=KlineRehearsalStatus.DRY_RUN,
        source_table=source,
        shadow_table=shadow,
        cleanup_on_success=cleanup_on_success,
        checks=tuple(
            KlineRehearsalCheck(
                code=code,
                status=KlineRehearsalCheckStatus.PLANNED,
            )
            for code in planned_codes
        ),
    )


def build_kline_rehearsal_failure_report(
    source_table: str,
    shadow_table: str,
    *,
    error_code: str,
    error_type: str,
    cleanup_on_success: bool = False,
    trace_id: str | None = None,
    now: datetime | None = None,
) -> KlineRehearsalReport:
    """Build a redacted failure report without retaining exception text."""
    return KlineRehearsalReport(
        trace_id=trace_id or uuid.uuid4().hex,
        generated_at=_format_time(now or datetime.now(UTC)),
        status=KlineRehearsalStatus.FAILED,
        source_table=_safe_identifier_for_report(source_table),
        shadow_table=_safe_identifier_for_report(shadow_table),
        cleanup_on_success=cleanup_on_success,
        checks=(
            KlineRehearsalCheck(
                code=KlineRehearsalCheckCode.EXECUTION,
                status=KlineRehearsalCheckStatus.FAILED,
            ),
        ),
        error_code=error_code,
        error_type=_safe_error_type(error_type),
    )


def run_kline_copy_rehearsal(
    engine: Engine,
    source_table: str,
    shadow_table: str,
    *,
    cleanup_on_success: bool = False,
    trace_id: str | None = None,
    now: datetime | None = None,
) -> KlineRehearsalReport:
    """Copy and validate K-line data in one PostgreSQL transaction."""
    effective_trace_id = trace_id or uuid.uuid4().hex
    generated_at = now or datetime.now(UTC)
    checks: list[KlineRehearsalCheck] = []
    transaction_started = False
    source = source_table
    shadow = shadow_table

    try:
        source = validate_rehearsal_source_table(source_table)
        shadow = validate_shadow_table_name(shadow_table)
        if engine.dialect.name.casefold() != "postgresql":
            raise UnsupportedPartitionDialectError("K-line rehearsal requires PostgreSQL.")
        plan = build_kline_partition_plan(shadow, now=generated_at)

        with engine.begin() as connection:
            transaction_started = True
            if connection.dialect.name.casefold() != "postgresql":
                raise UnsupportedPartitionDialectError("K-line rehearsal requires PostgreSQL.")

            connection.exec_driver_sql("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            _acquire_rehearsal_lock(connection)
            checks.append(
                KlineRehearsalCheck(
                    KlineRehearsalCheckCode.ISOLATION_LOCK,
                    KlineRehearsalCheckStatus.PASSED,
                    {
                        "advisory_xact_lock": True,
                        "isolation_level": "repeatable_read",
                    },
                )
            )
            _validate_source_and_shadow_namespace(connection, source, shadow, checks)

            source_evidence = _collect_aggregate_evidence(connection, source, "source")
            source_months = _collect_source_minute_months(connection, source)

            apply_kline_partition_plan(connection, plan)
            for statement in build_kline_source_month_partition_statements(shadow, source_months):
                connection.exec_driver_sql(statement)

            _copy_kline_rows(connection, source, shadow)
            shadow_evidence = _collect_aggregate_evidence(connection, shadow, "shadow")
            _validate_aggregate_evidence(
                checks,
                source_evidence,
                shadow_evidence,
                source_month_count=len(source_months),
            )

            sequence_next_value = _advance_and_read_shadow_sequence(
                connection,
                plan,
                shadow_evidence.max_id,
            )
            _require_check(
                checks,
                KlineRehearsalCheckCode.SEQUENCE_NEXT_VALUE,
                sequence_next_value > shadow_evidence.max_id,
                {
                    "max_id": shadow_evidence.max_id,
                    "next_value": sequence_next_value,
                },
            )

            foreign_key_evidence = _collect_foreign_key_evidence(connection, shadow)
            _require_check(
                checks,
                KlineRehearsalCheckCode.FOREIGN_KEYS,
                foreign_key_evidence["variety_cascade_count"] >= 1
                and foreign_key_evidence["contract_cascade_count"] >= 1,
                foreign_key_evidence,
            )

            query_scope = _select_core_query_scope(connection, source)
            source_query_rows = _run_core_query(connection, source, query_scope, "source")
            shadow_query_rows = _run_core_query(connection, shadow, query_scope, "shadow")
            _require_check(
                checks,
                KlineRehearsalCheckCode.CORE_QUERY,
                source_query_rows == shadow_query_rows and bool(source_query_rows),
                {
                    "source_rows": len(source_query_rows),
                    "shadow_rows": len(shadow_query_rows),
                    "limit": KLINE_REHEARSAL_QUERY_LIMIT,
                },
            )

            conflict_row_count = _verify_conflict_do_nothing(connection, source, shadow)
            _require_check(
                checks,
                KlineRehearsalCheckCode.CONFLICT_DO_NOTHING,
                conflict_row_count == 0,
                {"inserted_rows": conflict_row_count},
            )

            cascade_evidence = _verify_cascade_foreign_key(
                connection,
                shadow,
                trace_id=effective_trace_id,
                generated_at=generated_at,
            )
            _require_check(
                checks,
                KlineRehearsalCheckCode.CASCADE_FOREIGN_KEY,
                cascade_evidence["before_delete"] == 1
                and cascade_evidence["after_delete"] == 0
                and cascade_evidence["savepoint_rolled_back"],
                cascade_evidence,
            )

            pruning_evidence = _verify_partition_pruning(connection, shadow, query_scope)
            _require_check(
                checks,
                KlineRehearsalCheckCode.PARTITION_PRUNING,
                pruning_evidence["relation_names"] == [pruning_evidence["target_relation"]],
                pruning_evidence,
            )

            if cleanup_on_success:
                _drop_shadow_resources(connection, plan)
            checks.append(
                KlineRehearsalCheck(
                    KlineRehearsalCheckCode.CLEANUP,
                    KlineRehearsalCheckStatus.PASSED,
                    {"performed": cleanup_on_success},
                )
            )
    except Exception as exc:
        if transaction_started:
            checks.append(
                KlineRehearsalCheck(
                    KlineRehearsalCheckCode.TRANSACTION_ROLLBACK,
                    KlineRehearsalCheckStatus.PASSED,
                    {"rolled_back": True},
                )
            )
        if isinstance(exc, KlineRehearsalValidationError):
            error_code = exc.code.value
        elif isinstance(exc, ExistingShadowResourceError):
            error_code = KlineRehearsalCheckCode.SHADOW_NAMESPACE.value
        elif isinstance(exc, InvalidRehearsalSourceError):
            error_code = KlineRehearsalCheckCode.SOURCE_TABLE.value
        else:
            error_code = KlineRehearsalCheckCode.EXECUTION.value
            checks.append(
                KlineRehearsalCheck(
                    KlineRehearsalCheckCode.EXECUTION,
                    KlineRehearsalCheckStatus.FAILED,
                )
            )
        return KlineRehearsalReport(
            trace_id=effective_trace_id,
            generated_at=_format_time(generated_at),
            status=KlineRehearsalStatus.FAILED,
            source_table=_safe_identifier_for_report(source),
            shadow_table=_safe_identifier_for_report(shadow),
            cleanup_on_success=cleanup_on_success,
            checks=tuple(checks),
            error_code=error_code,
            error_type=_safe_error_type(type(exc).__name__),
        )

    return KlineRehearsalReport(
        trace_id=effective_trace_id,
        generated_at=_format_time(generated_at),
        status=KlineRehearsalStatus.PASSED,
        source_table=source,
        shadow_table=shadow,
        cleanup_on_success=cleanup_on_success,
        checks=tuple(checks),
    )


def _acquire_rehearsal_lock(connection: Connection) -> None:
    connection.execute(
        text(
            """
            /* kline_rehearsal:advisory_lock */
            SELECT pg_advisory_xact_lock(:lock_id)
            """
        ),
        {"lock_id": KLINE_REHEARSAL_ADVISORY_LOCK_ID},
    )


def _validate_source_and_shadow_namespace(
    connection: Connection,
    source_table: str,
    shadow_table: str,
    checks: list[KlineRehearsalCheck],
) -> None:
    source_exists = bool(
        connection.execute(
            text(
                """
                /* kline_rehearsal:source_exists */
                SELECT to_regclass(:source_table) IS NOT NULL
                """
            ),
            {"source_table": source_table},
        ).scalar_one()
    )
    _require_check(
        checks,
        KlineRehearsalCheckCode.SOURCE_TABLE,
        source_exists,
        {"exists": source_exists},
    )

    escaped_shadow = shadow_table.replace("\\", "\\\\").replace("_", "\\_").replace("%", "\\%")
    existing_count = int(
        connection.execute(
            text(
                """
                /* kline_rehearsal:shadow_namespace */
                SELECT COUNT(*)
                FROM pg_class
                WHERE relnamespace = to_regnamespace(current_schema())
                  AND (relname = :shadow_table OR relname LIKE :shadow_prefix ESCAPE '\\')
                """
            ),
            {
                "shadow_table": shadow_table,
                "shadow_prefix": f"{escaped_shadow}\\_%",
            },
        ).scalar_one()
    )
    if existing_count:
        checks.append(
            KlineRehearsalCheck(
                KlineRehearsalCheckCode.SHADOW_NAMESPACE,
                KlineRehearsalCheckStatus.FAILED,
                {"existing_resource_count": existing_count},
            )
        )
        raise ExistingShadowResourceError
    checks.append(
        KlineRehearsalCheck(
            KlineRehearsalCheckCode.SHADOW_NAMESPACE,
            KlineRehearsalCheckStatus.PASSED,
            {"existing_resource_count": 0},
        )
    )


def _collect_aggregate_evidence(
    connection: Connection,
    table_name: str,
    role: str,
) -> _KlineAggregateEvidence:
    kline_table = _kline_table(table_name)
    summary = (
        connection.execute(
            select(
                func.count().label("row_count"),
                func.min(kline_table.c.trading_time).label("min_trading_time"),
                func.max(kline_table.c.trading_time).label("max_trading_time"),
                func.coalesce(func.max(kline_table.c.id), 0).label("max_id"),
            )
            .select_from(kline_table)
            .prefix_with(f"/* kline_rehearsal:{role}_summary */")
        )
        .mappings()
        .one()
    )
    period_rows = (
        connection.execute(
            select(
                kline_table.c.period,
                func.count().label("row_count"),
            )
            .select_from(kline_table)
            .group_by(kline_table.c.period)
            .order_by(kline_table.c.period)
            .prefix_with(f"/* kline_rehearsal:{role}_period_counts */")
        )
        .mappings()
        .all()
    )
    duplicate_groups = (
        select(*[kline_table.c[name] for name in KLINE_NATURAL_KEY_COLUMNS])
        .select_from(kline_table)
        .group_by(*[kline_table.c[name] for name in KLINE_NATURAL_KEY_COLUMNS])
        .having(func.count() > 1)
        .subquery()
    )
    duplicate_count = int(
        connection.execute(
            select(func.count()).select_from(duplicate_groups).prefix_with(f"/* kline_rehearsal:{role}_duplicates */")
        ).scalar_one()
    )
    return _KlineAggregateEvidence(
        row_count=int(summary["row_count"]),
        period_counts={str(row["period"]): int(row["row_count"]) for row in period_rows},
        min_trading_time=summary["min_trading_time"],
        max_trading_time=summary["max_trading_time"],
        max_id=int(summary["max_id"]),
        duplicate_count=duplicate_count,
    )


def _collect_source_minute_months(
    connection: Connection,
    source_table: str,
) -> tuple[date | datetime, ...]:
    source = _kline_table(source_table)
    month_start = func.date_trunc("month", source.c.trading_time).label("month_start")
    values = (
        connection.execute(
            select(month_start)
            .select_from(source)
            .where(source.c.period.in_(KLINE_MINUTE_PERIOD_ALIASES))
            .distinct()
            .order_by(month_start)
            .prefix_with("/* kline_rehearsal:source_minute_months */")
        )
        .scalars()
        .all()
    )
    return tuple(values)


def _copy_kline_rows(
    connection: Connection,
    source_table: str,
    shadow_table: str,
) -> None:
    source = _kline_table(source_table)
    shadow = _kline_table(shadow_table)
    source_query = select(*[source.c[name] for name in KLINE_COPY_COLUMNS])
    statement = (
        postgresql.insert(shadow)
        .from_select(KLINE_COPY_COLUMNS, source_query)
        .prefix_with("/* kline_rehearsal:copy */")
    )
    connection.execute(statement)


def _validate_aggregate_evidence(
    checks: list[KlineRehearsalCheck],
    source: _KlineAggregateEvidence,
    shadow: _KlineAggregateEvidence,
    *,
    source_month_count: int,
) -> None:
    _require_check(
        checks,
        KlineRehearsalCheckCode.COPY_COUNT,
        source.row_count == shadow.row_count,
        {
            "source": source.row_count,
            "shadow": shadow.row_count,
            "source_minute_month_count": source_month_count,
        },
    )
    _require_check(
        checks,
        KlineRehearsalCheckCode.PERIOD_COUNTS,
        source.period_counts == shadow.period_counts,
        {
            "source": dict(sorted(source.period_counts.items())),
            "shadow": dict(sorted(shadow.period_counts.items())),
        },
    )
    source_bounds = {
        "min": _format_optional_time(source.min_trading_time),
        "max": _format_optional_time(source.max_trading_time),
    }
    shadow_bounds = {
        "min": _format_optional_time(shadow.min_trading_time),
        "max": _format_optional_time(shadow.max_trading_time),
    }
    _require_check(
        checks,
        KlineRehearsalCheckCode.TRADING_TIME_BOUNDS,
        source_bounds == shadow_bounds,
        {"source": source_bounds, "shadow": shadow_bounds},
    )
    _require_check(
        checks,
        KlineRehearsalCheckCode.NATURAL_KEY_DUPLICATES,
        shadow.duplicate_count == 0,
        {"duplicate_count": shadow.duplicate_count},
    )


def _advance_and_read_shadow_sequence(
    connection: Connection,
    plan: KlinePartitionPlan,
    max_id: int,
) -> int:
    connection.execute(
        text(
            """
            /* kline_rehearsal:sequence_set */
            SELECT setval(CAST(:sequence_name AS regclass), :next_value, false)
            """
        ),
        {
            "sequence_name": plan.sequence_name,
            "next_value": max_id + 1,
        },
    )
    return int(
        connection.execute(
            text(
                """
                /* kline_rehearsal:sequence_next */
                SELECT nextval(CAST(:sequence_name AS regclass))
                """
            ),
            {"sequence_name": plan.sequence_name},
        ).scalar_one()
    )


def _collect_foreign_key_evidence(
    connection: Connection,
    shadow_table: str,
) -> dict[str, int]:
    row = (
        connection.execute(
            text(
                """
                /* kline_rehearsal:foreign_keys */
                SELECT
                    COUNT(*) FILTER (
                        WHERE confrelid = to_regclass('varieties')
                          AND confdeltype = 'c'
                    ) AS variety_cascade_count,
                    COUNT(*) FILTER (
                        WHERE confrelid = to_regclass('fut_contracts')
                          AND confdeltype = 'c'
                    ) AS contract_cascade_count
                FROM pg_constraint
                WHERE conrelid = to_regclass(:shadow_table)
                  AND contype = 'f'
                """
            ),
            {"shadow_table": shadow_table},
        )
        .mappings()
        .one()
    )
    return {
        "variety_cascade_count": int(row["variety_cascade_count"]),
        "contract_cascade_count": int(row["contract_cascade_count"]),
    }


def _select_core_query_scope(
    connection: Connection,
    source_table: str,
) -> Mapping[str, Any]:
    source = _kline_table(source_table)
    row = (
        connection.execute(
            select(
                source.c.variety_id,
                source.c.contract_id,
                source.c.period,
                func.min(source.c.trading_time).label("start_time"),
                func.max(source.c.trading_time).label("end_time"),
                func.count().label("row_count"),
            )
            .select_from(source)
            .where(source.c.period.in_(KLINE_MINUTE_PERIOD_ALIASES))
            .group_by(source.c.variety_id, source.c.contract_id, source.c.period)
            .order_by(func.count().desc(), source.c.variety_id, source.c.contract_id, source.c.period)
            .limit(1)
            .prefix_with("/* kline_rehearsal:core_query_scope */")
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise KlineRehearsalValidationError(KlineRehearsalCheckCode.CORE_QUERY)
    return row


def _run_core_query(
    connection: Connection,
    table_name: str,
    scope: Mapping[str, Any],
    role: str,
) -> list[tuple[Any, ...]]:
    kline_table = _kline_table(table_name)
    return list(
        connection.execute(
            select(kline_table.c.id, kline_table.c.trading_time)
            .select_from(kline_table)
            .where(
                kline_table.c.variety_id == scope["variety_id"],
                kline_table.c.contract_id == scope["contract_id"],
                kline_table.c.period == scope["period"],
                kline_table.c.trading_time >= scope["start_time"],
                kline_table.c.trading_time <= scope["end_time"],
            )
            .order_by(kline_table.c.trading_time.desc())
            .limit(KLINE_REHEARSAL_QUERY_LIMIT)
            .prefix_with(f"/* kline_rehearsal:{role}_core_query */")
        ).all()
    )


def _verify_conflict_do_nothing(
    connection: Connection,
    source_table: str,
    shadow_table: str,
) -> int:
    source = _kline_table(source_table)
    shadow = _kline_table(shadow_table)
    duplicate_row = select(*[source.c[name] for name in KLINE_COPY_COLUMNS]).order_by(source.c.id).limit(1)
    statement = (
        postgresql.insert(shadow)
        .from_select(KLINE_COPY_COLUMNS, duplicate_row)
        .on_conflict_do_nothing(index_elements=[shadow.c[name] for name in KLINE_NATURAL_KEY_COLUMNS])
        .prefix_with("/* kline_rehearsal:conflict_do_nothing */")
    )
    result = connection.execute(statement)
    return int(result.rowcount)


def _verify_cascade_foreign_key(
    connection: Connection,
    shadow_table: str,
    *,
    trace_id: str,
    generated_at: datetime,
) -> dict[str, int | bool]:
    marker = trace_id[:8]
    symbol = f"R8{marker}"
    contract_code = f"{symbol}99"
    varieties = table(
        "varieties",
        column("id"),
        column("symbol"),
        column("contract_code"),
        column("name"),
        column("exchange"),
        column("category"),
    )
    contracts = table(
        "fut_contracts",
        column("id"),
        column("ts_code"),
        column("symbol"),
        column("name"),
        column("fut_code"),
        column("exchange"),
        column("is_active"),
    )
    shadow = _kline_table(shadow_table)

    savepoint = connection.begin_nested()
    rolled_back = False
    try:
        variety_id = connection.execute(
            postgresql.insert(varieties)
            .values(
                symbol=symbol,
                contract_code=contract_code,
                name="R8 rehearsal",
                exchange="TEST",
                category="rehearsal",
            )
            .returning(varieties.c.id)
            .prefix_with("/* kline_rehearsal:cascade_variety */")
        ).scalar_one()
        contract_id = connection.execute(
            postgresql.insert(contracts)
            .values(
                ts_code=f"{contract_code}.T",
                symbol=contract_code,
                name="R8 rehearsal",
                fut_code=symbol,
                exchange="TEST",
                is_active=False,
            )
            .returning(contracts.c.id)
            .prefix_with("/* kline_rehearsal:cascade_contract */")
        ).scalar_one()
        connection.execute(
            postgresql.insert(shadow)
            .values(
                variety_id=variety_id,
                contract_id=contract_id,
                period="1d",
                trading_time=generated_at,
                trading_date=generated_at.date(),
                open_price=1,
                high_price=1,
                low_price=1,
                close_price=1,
                volume=0,
                open_interest=0,
                created_at=generated_at,
            )
            .prefix_with("/* kline_rehearsal:cascade_shadow_row */")
        )
        before_delete = int(
            connection.execute(
                select(func.count())
                .select_from(shadow)
                .where(shadow.c.contract_id == contract_id)
                .prefix_with("/* kline_rehearsal:cascade_before */")
            ).scalar_one()
        )
        connection.execute(
            delete(contracts).where(contracts.c.id == contract_id).prefix_with("/* kline_rehearsal:cascade_delete */")
        )
        after_delete = int(
            connection.execute(
                select(func.count())
                .select_from(shadow)
                .where(shadow.c.contract_id == contract_id)
                .prefix_with("/* kline_rehearsal:cascade_after */")
            ).scalar_one()
        )
    finally:
        savepoint.rollback()
        rolled_back = True
    return {
        "before_delete": before_delete,
        "after_delete": after_delete,
        "savepoint_rolled_back": rolled_back,
    }


def _verify_partition_pruning(
    connection: Connection,
    shadow_table: str,
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    start_time = _as_utc_datetime(scope["start_time"])
    month_start = datetime(start_time.year, start_time.month, 1, tzinfo=UTC)
    month_end = _add_months(month_start, 1)
    target_relation = (
        f"{shadow_table}{KLINE_MONTH_PARTITION_FORMAT.format(year=month_start.year, month=month_start.month)}"
    )
    raw_plan = connection.execute(
        text(
            f"""
            /* kline_rehearsal:partition_pruning */
            EXPLAIN (FORMAT JSON)
            SELECT id
            FROM {_quote_identifier(shadow_table)}
            WHERE variety_id = :variety_id
              AND contract_id = :contract_id
              AND period = :period
              AND trading_time >= :start_time
              AND trading_time < :end_time
            ORDER BY trading_time DESC
            LIMIT :query_limit
            """
        ),
        {
            "variety_id": scope["variety_id"],
            "contract_id": scope["contract_id"],
            "period": scope["period"],
            "start_time": month_start,
            "end_time": month_end,
            "query_limit": KLINE_REHEARSAL_QUERY_LIMIT,
        },
    ).scalar_one()
    relation_names = sorted(_extract_plan_relation_names(raw_plan))
    return {
        "target_relation": target_relation,
        "relation_names": relation_names,
    }


def _extract_plan_relation_names(raw_plan: Any) -> set[str]:
    parsed = json.loads(raw_plan) if isinstance(raw_plan, str) else raw_plan
    document = parsed[0] if isinstance(parsed, list) else parsed
    if not isinstance(document, Mapping) or not isinstance(document.get("Plan"), Mapping):
        raise KlineRehearsalValidationError(KlineRehearsalCheckCode.PARTITION_PRUNING)

    relation_names: set[str] = set()
    stack = [document["Plan"]]
    while stack:
        node = stack.pop()
        relation_name = node.get("Relation Name")
        if isinstance(relation_name, str):
            relation_names.add(relation_name)
        children = node.get("Plans", ())
        if isinstance(children, list):
            stack.extend(child for child in children if isinstance(child, Mapping))
    return relation_names


def _drop_shadow_resources(
    connection: Connection,
    plan: KlinePartitionPlan,
) -> None:
    connection.exec_driver_sql(f"DROP TABLE IF EXISTS {_quote_identifier(plan.shadow_table)} CASCADE")
    connection.exec_driver_sql(f"DROP SEQUENCE IF EXISTS {_quote_identifier(plan.sequence_name)}")


def _require_check(
    checks: list[KlineRehearsalCheck],
    code: KlineRehearsalCheckCode,
    condition: bool,
    evidence: Mapping[str, Any],
) -> None:
    checks.append(
        KlineRehearsalCheck(
            code,
            (KlineRehearsalCheckStatus.PASSED if condition else KlineRehearsalCheckStatus.FAILED),
            evidence,
        )
    )
    if not condition:
        raise KlineRehearsalValidationError(code)


def _kline_table(table_name: str):
    return table(table_name, *(column(name) for name in KLINE_COPY_COLUMNS))


def _quote_identifier(identifier: str) -> str:
    return _POSTGRES_DIALECT.identifier_preparer.quote_identifier(identifier)


def _as_utc_datetime(value: Any) -> datetime:
    if not isinstance(value, datetime):
        raise KlineRehearsalValidationError(KlineRehearsalCheckCode.PARTITION_PRUNING)
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC)


def _add_months(value: datetime, offset: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 + offset
    return datetime(month_index // 12, month_index % 12 + 1, 1, tzinfo=UTC)


def _format_optional_time(value: Any) -> str | None:
    if value is None:
        return None
    return _format_time(value)


def _format_time(value: Any) -> str:
    if isinstance(value, datetime):
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _safe_error_type(value: str) -> str:
    return value if _SAFE_ERROR_TYPE_PATTERN.fullmatch(value) else "DatabaseError"


def _safe_identifier_for_report(value: str) -> str:
    try:
        if value == KLINE_ACTIVE_TABLE:
            return value
        return validate_shadow_table_name(value)
    except Exception:
        return "invalid_identifier"
