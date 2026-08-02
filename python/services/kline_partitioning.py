"""PostgreSQL shadow partition planning for K-line data."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import Connection
from sqlalchemy.sql.sqltypes import String

from services.kline_storage import KLINE_FUTURE_MONTHS

KLINE_MINUTE_PERIOD_ALIASES = (
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
KLINE_LONG_PERIOD_ALIASES = ("1d", "D", "1w", "W", "M")
KLINE_ACTIVE_TABLE = "kline_data"
KLINE_SHADOW_NAME_TOKEN = "shadow"
KLINE_PARTITION_FUTURE_MONTHS = KLINE_FUTURE_MONTHS

KLINE_SEQUENCE_SUFFIX = "_id_seq"
KLINE_MINUTE_PARTITION_SUFFIX = "_minute"
KLINE_LONG_PARTITION_SUFFIX = "_long"
KLINE_DEFAULT_PARTITION_SUFFIX = "_default"
KLINE_MONTH_PARTITION_FORMAT = "_minute_{year:04d}{month:02d}"

_POSTGRES_IDENTIFIER_MAX_BYTES = 63
_SAFE_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_POSTGRES_DIALECT = postgresql.dialect()
_STRING_LITERAL_PROCESSOR = String().literal_processor(_POSTGRES_DIALECT)


class KlinePartitioningError(RuntimeError):
    """Base error for a rejected partition operation."""


class InvalidShadowTableError(KlinePartitioningError, ValueError):
    """Raised when a shadow table identifier is unsafe."""


class ActiveKlineTableRejectedError(KlinePartitioningError, ValueError):
    """Raised when an operation targets the active K-line table."""


class UnsafeShadowTableError(KlinePartitioningError, ValueError):
    """Raised when a target is not explicitly named as a shadow table."""


class UnsupportedPartitionDialectError(KlinePartitioningError):
    """Raised when DDL execution is attempted outside PostgreSQL."""


@dataclass(frozen=True)
class KlineMonthPartition:
    """One monthly range partition below the minute LIST partition."""

    table_name: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class KlinePartitionPlan:
    """Stable, explicit DDL plan for one shadow table."""

    shadow_table: str
    sequence_name: str
    minute_table: str
    long_table: str
    default_table: str
    month_partitions: tuple[KlineMonthPartition, ...]
    statements: tuple[str, ...]

    def to_sql(self) -> str:
        """Render executable statements in deterministic order."""
        return "\n\n".join(f"{statement};" for statement in self.statements)


def validate_shadow_table_name(shadow_table: str) -> str:
    """Validate an unqualified PostgreSQL shadow table identifier."""
    if not isinstance(shadow_table, str) or not _SAFE_IDENTIFIER_PATTERN.fullmatch(shadow_table):
        raise InvalidShadowTableError("Shadow table must be an unqualified ASCII PostgreSQL identifier.")
    if shadow_table.casefold() == KLINE_ACTIVE_TABLE:
        raise ActiveKlineTableRejectedError("The active kline_data table is never a valid target.")
    if KLINE_SHADOW_NAME_TOKEN not in shadow_table.casefold().split("_"):
        raise UnsafeShadowTableError("Shadow table name must contain a standalone 'shadow' token.")

    for identifier in _all_generated_identifiers(shadow_table):
        if len(identifier.encode("utf-8")) > _POSTGRES_IDENTIFIER_MAX_BYTES:
            raise InvalidShadowTableError("Shadow table name is too long for generated PostgreSQL identifiers.")
    return shadow_table


def build_kline_partition_plan(
    shadow_table: str,
    *,
    now: date | datetime | None = None,
) -> KlinePartitionPlan:
    """Build current-model shadow DDL and the next three minute partitions."""
    validated_table = validate_shadow_table_name(shadow_table)
    sequence_name = f"{validated_table}{KLINE_SEQUENCE_SUFFIX}"
    minute_table = f"{validated_table}{KLINE_MINUTE_PARTITION_SUFFIX}"
    long_table = f"{validated_table}{KLINE_LONG_PARTITION_SUFFIX}"
    default_table = f"{validated_table}{KLINE_DEFAULT_PARTITION_SUFFIX}"
    month_partitions = _future_month_partitions(validated_table, now)

    statements = (
        _create_sequence_ddl(sequence_name),
        _create_parent_table_ddl(validated_table, sequence_name),
        _create_list_partition_ddl(
            minute_table,
            validated_table,
            KLINE_MINUTE_PERIOD_ALIASES,
            secondary_partition="RANGE (trading_time)",
        ),
        _create_list_partition_ddl(
            long_table,
            validated_table,
            KLINE_LONG_PERIOD_ALIASES,
        ),
        _create_default_partition_ddl(default_table, validated_table),
        *(_create_month_partition_ddl(partition, minute_table) for partition in month_partitions),
        *_create_index_ddls(validated_table),
    )
    return KlinePartitionPlan(
        shadow_table=validated_table,
        sequence_name=sequence_name,
        minute_table=minute_table,
        long_table=long_table,
        default_table=default_table,
        month_partitions=month_partitions,
        statements=statements,
    )


def build_kline_source_month_partition_statements(
    shadow_table: str,
    month_starts: tuple[date | datetime, ...],
) -> tuple[str, ...]:
    """Build idempotent minute partitions for months present in source data."""
    validated_table = validate_shadow_table_name(shadow_table)
    minute_table = f"{validated_table}{KLINE_MINUTE_PARTITION_SUFFIX}"
    normalized_months = set()
    for value in month_starts:
        if isinstance(value, datetime):
            normalized = value
            if normalized.tzinfo is None:
                normalized = normalized.replace(tzinfo=UTC)
            current = normalized.astimezone(UTC).date()
        else:
            current = value
        normalized_months.add(date(current.year, current.month, 1))

    statements = []
    for month_start in sorted(normalized_months):
        month_end = _add_months(month_start, 1)
        partition = KlineMonthPartition(
            table_name=(
                f"{validated_table}"
                f"{KLINE_MONTH_PARTITION_FORMAT.format(year=month_start.year, month=month_start.month)}"
            ),
            start=datetime(month_start.year, month_start.month, 1, tzinfo=UTC),
            end=datetime(month_end.year, month_end.month, 1, tzinfo=UTC),
        )
        statements.append(_create_month_partition_ddl(partition, minute_table))
    return tuple(statements)


def apply_kline_partition_plan(
    connection: Connection,
    plan: KlinePartitionPlan,
) -> int:
    """Apply an idempotent plan using an existing PostgreSQL transaction."""
    validate_shadow_table_name(plan.shadow_table)
    dialect = getattr(connection, "dialect", None)
    dialect_name = str(getattr(dialect, "name", "")).casefold()
    if dialect_name != "postgresql":
        raise UnsupportedPartitionDialectError("K-line partition DDL can only be applied to PostgreSQL.")

    for statement in plan.statements:
        connection.exec_driver_sql(statement)
    return len(plan.statements)


def _all_generated_identifiers(shadow_table: str) -> tuple[str, ...]:
    suffixes = (
        KLINE_SEQUENCE_SUFFIX,
        KLINE_MINUTE_PARTITION_SUFFIX,
        KLINE_LONG_PARTITION_SUFFIX,
        KLINE_DEFAULT_PARTITION_SUFFIX,
        "_pkey",
        "_natural_key",
        "_variety_fk",
        "_contract_fk",
        "_contract_id_idx",
        "_trading_date_idx",
        "_lookup_idx",
        "_contract_period_time_idx",
        KLINE_MONTH_PARTITION_FORMAT.format(year=9999, month=12),
    )
    return (shadow_table, *(f"{shadow_table}{suffix}" for suffix in suffixes))


def _future_month_partitions(
    shadow_table: str,
    now: date | datetime | None,
) -> tuple[KlineMonthPartition, ...]:
    current = now or datetime.now(UTC)
    if isinstance(current, datetime):
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        current_date = current.astimezone(UTC).date()
    else:
        current_date = current

    current_month = date(current_date.year, current_date.month, 1)
    partitions = []
    for offset in range(1, KLINE_PARTITION_FUTURE_MONTHS + 1):
        start_date = _add_months(current_month, offset)
        end_date = _add_months(start_date, 1)
        partitions.append(
            KlineMonthPartition(
                table_name=(
                    f"{shadow_table}{KLINE_MONTH_PARTITION_FORMAT.format(year=start_date.year, month=start_date.month)}"
                ),
                start=datetime(start_date.year, start_date.month, 1, tzinfo=UTC),
                end=datetime(end_date.year, end_date.month, 1, tzinfo=UTC),
            )
        )
    return tuple(partitions)


def _add_months(value: date, offset: int) -> date:
    month_index = value.year * 12 + value.month - 1 + offset
    return date(month_index // 12, month_index % 12 + 1, 1)


def _create_sequence_ddl(sequence_name: str) -> str:
    return f"CREATE SEQUENCE IF NOT EXISTS {_quote_identifier(sequence_name)} AS INTEGER"


def _create_parent_table_ddl(shadow_table: str, sequence_name: str) -> str:
    table = _quote_identifier(shadow_table)
    sequence_regclass = _quote_identifier(sequence_name)
    columns = (
        f"    {_quote_identifier('id')} INTEGER NOT NULL DEFAULT nextval({_literal(sequence_regclass)}::regclass)",
        f"    {_quote_identifier('variety_id')} INTEGER NOT NULL",
        f"    {_quote_identifier('contract_id')} INTEGER NOT NULL",
        f"    {_quote_identifier('period')} VARCHAR(10) NOT NULL",
        f"    {_quote_identifier('trading_time')} TIMESTAMP WITH TIME ZONE NOT NULL",
        f"    {_quote_identifier('trading_date')} DATE",
        f"    {_quote_identifier('open_price')} NUMERIC(19, 4) NOT NULL",
        f"    {_quote_identifier('high_price')} NUMERIC(19, 4) NOT NULL",
        f"    {_quote_identifier('low_price')} NUMERIC(19, 4) NOT NULL",
        f"    {_quote_identifier('close_price')} NUMERIC(19, 4) NOT NULL",
        f"    {_quote_identifier('volume')} INTEGER NOT NULL",
        f"    {_quote_identifier('open_interest')} INTEGER",
        f"    {_quote_identifier('created_at')} TIMESTAMP WITH TIME ZONE",
        (
            f"    CONSTRAINT {_quote_identifier(f'{shadow_table}_pkey')} "
            f"PRIMARY KEY ({_column_list('id', 'period', 'trading_time')})"
        ),
        (
            f"    CONSTRAINT {_quote_identifier(f'{shadow_table}_natural_key')} "
            "UNIQUE "
            f"({_column_list('variety_id', 'contract_id', 'period', 'trading_time')})"
        ),
        (
            f"    CONSTRAINT {_quote_identifier(f'{shadow_table}_variety_fk')} "
            f"FOREIGN KEY ({_quote_identifier('variety_id')}) "
            f"REFERENCES {_quote_identifier('varieties')} ({_quote_identifier('id')}) "
            "ON DELETE CASCADE"
        ),
        (
            f"    CONSTRAINT {_quote_identifier(f'{shadow_table}_contract_fk')} "
            f"FOREIGN KEY ({_quote_identifier('contract_id')}) "
            f"REFERENCES {_quote_identifier('fut_contracts')} ({_quote_identifier('id')}) "
            "ON DELETE CASCADE"
        ),
    )
    rendered_columns = ",\n".join(columns)
    return (
        f"CREATE TABLE IF NOT EXISTS {table} (\n{rendered_columns}\n) PARTITION BY LIST ({_quote_identifier('period')})"
    )


def _create_list_partition_ddl(
    partition_table: str,
    parent_table: str,
    aliases: tuple[str, ...],
    *,
    secondary_partition: str | None = None,
) -> str:
    values = ", ".join(_literal(alias) for alias in aliases)
    ddl = (
        f"CREATE TABLE IF NOT EXISTS {_quote_identifier(partition_table)} "
        f"PARTITION OF {_quote_identifier(parent_table)} "
        f"FOR VALUES IN ({values})"
    )
    if secondary_partition is not None:
        ddl = f"{ddl} PARTITION BY {secondary_partition}"
    return ddl


def _create_default_partition_ddl(
    default_table: str,
    parent_table: str,
) -> str:
    return (
        f"CREATE TABLE IF NOT EXISTS {_quote_identifier(default_table)} "
        f"PARTITION OF {_quote_identifier(parent_table)} DEFAULT"
    )


def _create_month_partition_ddl(
    partition: KlineMonthPartition,
    minute_table: str,
) -> str:
    start = _timestamp_literal(partition.start)
    end = _timestamp_literal(partition.end)
    return (
        f"CREATE TABLE IF NOT EXISTS {_quote_identifier(partition.table_name)} "
        f"PARTITION OF {_quote_identifier(minute_table)} "
        f"FOR VALUES FROM ({start}) TO ({end})"
    )


def _create_index_ddls(shadow_table: str) -> tuple[str, ...]:
    table = _quote_identifier(shadow_table)
    specifications = (
        ("contract_id_idx", ("contract_id",)),
        ("trading_date_idx", ("trading_date",)),
        ("lookup_idx", ("variety_id", "period", "trading_time")),
        (
            "contract_period_time_idx",
            ("contract_id", "period", "trading_time"),
        ),
    )
    return tuple(
        (
            f"CREATE INDEX IF NOT EXISTS "
            f"{_quote_identifier(f'{shadow_table}_{suffix}')} "
            f"ON {table} ({_column_list(*columns)})"
        )
        for suffix, columns in specifications
    )


def _column_list(*columns: str) -> str:
    return ", ".join(_quote_identifier(column) for column in columns)


def _quote_identifier(identifier: str) -> str:
    return _POSTGRES_DIALECT.identifier_preparer.quote_identifier(identifier)


def _literal(value: str) -> str:
    if _STRING_LITERAL_PROCESSOR is None:
        raise AssertionError("PostgreSQL string literal processor is unavailable.")
    return _STRING_LITERAL_PROCESSOR(value)


def _timestamp_literal(value: datetime) -> str:
    normalized = value.astimezone(UTC)
    rendered = normalized.strftime("%Y-%m-%d %H:%M:%S+00")
    return f"TIMESTAMPTZ {_literal(rendered)}"
