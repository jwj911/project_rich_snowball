"""K-line storage capacity preflight with read-only, redacted evidence."""

from __future__ import annotations

import json
import math
import re
import uuid
from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from threading import RLock
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

KLINE_ROW_COUNT_THRESHOLD = 100_000_000
KLINE_TOTAL_BYTES_THRESHOLD = 100 * 1024**3
KLINE_MINUTE_QUERY_P99_THRESHOLD_MS = 500.0
KLINE_FUTURE_MONTHS = 3
KLINE_STORAGE_OVERVIEW_TTL_SECONDS = 60.0

_URL_CREDENTIALS_PATTERN = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s@]+)@")
_NAMED_SECRET_PATTERN = re.compile(
    r"(?i)\b([a-z0-9_.-]*(?:password|passwd|secret(?:_key)?|api[_-]?key|token))"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_PARTITION_RANGE_PATTERN = re.compile(
    r"FROM\s*\(\s*'([^']+)'\s*(?:::[^)]+)?\)\s*TO\s*\(\s*'([^']+)'\s*(?:::[^)]+)?\)",
    re.IGNORECASE,
)
_SAFE_ERROR_TYPE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")


class KlineStorageCheckCode(StrEnum):
    """Stable codes for storage evidence and threshold checks."""

    COLLECTION = "KLINE_STORAGE_COLLECTION"
    DATABASE_DIALECT = "KLINE_DATABASE_DIALECT"
    DATABASE_VERSION = "KLINE_DATABASE_VERSION"
    ROW_COUNT_THRESHOLD = "KLINE_ROW_COUNT_THRESHOLD"
    TOTAL_BYTES_THRESHOLD = "KLINE_TOTAL_BYTES_THRESHOLD"
    PERIOD_DISTRIBUTION = "KLINE_PERIOD_DISTRIBUTION"
    PARTITION_STATE = "KLINE_PARTITION_STATE"
    FUTURE_MONTH_COVERAGE = "KLINE_FUTURE_MONTH_COVERAGE"
    MINUTE_QUERY_PLAN = "KLINE_MINUTE_QUERY_PLAN"
    MINUTE_QUERY_P99_THRESHOLD = "KLINE_MINUTE_QUERY_P99_THRESHOLD"


class KlineStorageCheckStatus(StrEnum):
    """Stable status values for an individual check."""

    PASSED = "passed"
    TRIGGERED = "triggered"
    WARNING = "warning"
    NOT_AVAILABLE = "not_available"
    NOT_APPLICABLE = "not_applicable"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class KlineStorageStatus(StrEnum):
    """Overall preflight conclusion."""

    NOT_REQUIRED = "not_required"
    RECOMMENDED = "recommended"
    INCONCLUSIVE = "inconclusive"
    UNSUPPORTED_FOR_PARTITIONING = "unsupported_for_partitioning"
    FAILED = "failed"


@dataclass(frozen=True)
class KlineStorageCheck:
    """One stable, non-sensitive preflight result."""

    code: KlineStorageCheckCode
    status: KlineStorageCheckStatus
    summary: str

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code.value,
            "status": self.status.value,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class KlinePeriodStats:
    """Aggregate evidence for one stored period."""

    period: str
    row_count: int
    min_trading_time: str | None
    max_trading_time: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "row_count": self.row_count,
            "min_trading_time": self.min_trading_time,
            "max_trading_time": self.max_trading_time,
        }


@dataclass(frozen=True)
class KlineStorageBytes:
    """PostgreSQL relation sizes in bytes."""

    table: int | None
    indexes: int | None
    total: int | None

    def to_dict(self) -> dict[str, int | None]:
        return {
            "table": self.table,
            "indexes": self.indexes,
            "total": self.total,
        }


@dataclass(frozen=True)
class KlineStorageOverview:
    """Low-cost storage summary suitable for an authenticated request path."""

    dialect: str
    storage_bytes: KlineStorageBytes
    row_estimate: int | None
    row_count: int | None
    partitioning_supported: bool
    is_partitioned: bool
    partition_count: int
    required_future_months: tuple[str, ...]
    missing_future_months: tuple[str, ...]
    last_collection_time: str | None
    collected_at: str

    def to_dict(self) -> dict[str, Any]:
        coverage_complete = (
            self.is_partitioned and not self.missing_future_months if self.partitioning_supported else None
        )
        return {
            "dialect": self.dialect,
            "storage_bytes": self.storage_bytes.to_dict(),
            "row_estimate": self.row_estimate,
            "row_count": self.row_count,
            "partitioning_supported": self.partitioning_supported,
            "is_partitioned": self.is_partitioned,
            "partition_count": self.partition_count,
            "future_coverage": {
                "required_months": list(self.required_future_months),
                "missing_months": list(self.missing_future_months),
                "complete": coverage_complete,
            },
            "last_collection_time": self.last_collection_time,
            "collected_at": self.collected_at,
        }


@dataclass(frozen=True)
class _KlineStorageOverviewCacheEntry:
    overview: KlineStorageOverview
    expires_at: float


class KlineStorageOverviewCache:
    """Small in-process TTL cache with deterministic expiry and explicit invalidation."""

    def __init__(
        self,
        ttl_seconds: float = KLINE_STORAGE_OVERVIEW_TTL_SECONDS,
        *,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be non-negative")
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[object, _KlineStorageOverviewCacheEntry] = {}
        self._lock = RLock()

    def get(
        self,
        bind: Engine | Connection,
        *,
        now: datetime | None = None,
    ) -> KlineStorageOverview:
        current = self._clock()
        with self._lock:
            cached = self._entries.get(bind)
            if cached is not None and current < cached.expires_at:
                return cached.overview

            overview = collect_kline_storage_overview(bind, now=now)
            self._entries[bind] = _KlineStorageOverviewCacheEntry(
                overview=overview,
                expires_at=current + self.ttl_seconds,
            )
            return overview

    def invalidate(self, bind: Engine | Connection | None = None) -> None:
        with self._lock:
            if bind is None:
                self._entries.clear()
            else:
                self._entries.pop(bind, None)


_kline_storage_overview_cache = KlineStorageOverviewCache()


@dataclass(frozen=True)
class KlinePartitionState:
    """Current partition state and required future month coverage."""

    supported: bool
    is_partitioned: bool
    partition_count: int
    required_future_months: tuple[str, ...]
    missing_future_months: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "supported": self.supported,
            "is_partitioned": self.is_partitioned,
            "partition_count": self.partition_count,
            "required_future_months": list(self.required_future_months),
            "missing_future_months": list(self.missing_future_months),
        }


@dataclass(frozen=True)
class KlineQueryPlanSummary:
    """Whitelisted EXPLAIN fields that cannot contain SQL parameter values."""

    query_code: str
    root_node_type: str
    node_type_counts: Mapping[str, int]
    relation_names: tuple[str, ...]
    index_names: tuple[str, ...]
    startup_cost: float | None
    total_cost: float | None
    plan_rows: int | None
    subplans_removed: int
    planning_time_ms: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "query_code": self.query_code,
            "root_node_type": self.root_node_type,
            "node_type_counts": dict(self.node_type_counts),
            "relation_names": list(self.relation_names),
            "index_names": list(self.index_names),
            "startup_cost": self.startup_cost,
            "total_cost": self.total_cost,
            "plan_rows": self.plan_rows,
            "subplans_removed": self.subplans_removed,
            "planning_time_ms": self.planning_time_ms,
        }


@dataclass(frozen=True)
class KlineStorageEvidence:
    """Collected aggregate storage evidence."""

    dialect: str
    database_version: str
    row_count: int
    row_count_kind: str
    storage_bytes: KlineStorageBytes
    periods: tuple[KlinePeriodStats, ...]
    partitioning: KlinePartitionState
    minute_query_p99_ms: float | None
    minute_query_plans: tuple[KlineQueryPlanSummary, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "dialect": self.dialect,
            "database_version": self.database_version,
            "row_count": self.row_count,
            "row_count_kind": self.row_count_kind,
            "storage_bytes": self.storage_bytes.to_dict(),
            "periods": [period.to_dict() for period in self.periods],
            "partitioning": self.partitioning.to_dict(),
            "minute_query": {
                "p99_ms": self.minute_query_p99_ms,
                "plans": [plan.to_dict() for plan in self.minute_query_plans],
            },
        }


@dataclass(frozen=True)
class KlineStorageReport:
    """A traceable K-line storage preflight report."""

    trace_id: str
    generated_at: str
    status: KlineStorageStatus
    checks: tuple[KlineStorageCheck, ...]
    evidence: KlineStorageEvidence | None
    trigger_codes: tuple[KlineStorageCheckCode, ...] = ()
    error_type: str | None = None
    sensitive_values: tuple[str, ...] = field(default=(), repr=False, compare=False)
    schema_version: int = 1

    @property
    def gate_passed(self) -> bool:
        """Whether no partition threshold was reached and all thresholds were available."""
        return self.status is KlineStorageStatus.NOT_REQUIRED

    def to_dict(self) -> dict[str, Any]:
        status_counts = Counter(check.status.value for check in self.checks)
        payload = {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "generated_at": self.generated_at,
            "status": self.status.value,
            "thresholds": {
                "row_count": KLINE_ROW_COUNT_THRESHOLD,
                "total_bytes": KLINE_TOTAL_BYTES_THRESHOLD,
                "minute_query_p99_ms": KLINE_MINUTE_QUERY_P99_THRESHOLD_MS,
            },
            "summary": {
                "check_total": len(self.checks),
                "status_counts": dict(sorted(status_counts.items())),
                "trigger_codes": [code.value for code in self.trigger_codes],
            },
            "checks": [check.to_dict() for check in self.checks],
            "evidence": self.evidence.to_dict() if self.evidence is not None else None,
            "error": (
                {
                    "code": KlineStorageCheckCode.COLLECTION.value,
                    "error_type": self.error_type,
                }
                if self.error_type
                else None
            ),
        }
        return _redact_json_value(payload, self.sensitive_values)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=True, indent=2)


def redact_sensitive_text(value: object, sensitive_values: Sequence[str] = ()) -> str:
    """Redact known secrets, provider tokens, and URL credentials from text."""
    redacted = str(value)
    for secret in sorted({item for item in sensitive_values if item}, key=len, reverse=True):
        redacted = redacted.replace(secret, "***")
    redacted = _URL_CREDENTIALS_PATTERN.sub(r"\1***@", redacted)
    return _NAMED_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}***", redacted)


def database_url_sensitive_values(database_url: str | None) -> tuple[str, ...]:
    """Return URL values that must never be copied into diagnostics."""
    if not database_url:
        return ()
    values = [database_url]
    try:
        password = urlsplit(database_url).password
    except ValueError:
        password = None
    if password:
        values.append(password)
    return tuple(values)


def build_kline_storage_failure_report(
    error_type: str,
    *,
    trace_id: str | None = None,
    now: datetime | None = None,
    sensitive_values: Sequence[str] = (),
) -> KlineStorageReport:
    """Build a redacted failure report without retaining an exception message."""
    return KlineStorageReport(
        trace_id=trace_id or uuid.uuid4().hex,
        generated_at=_format_generated_at(now),
        status=KlineStorageStatus.FAILED,
        checks=(
            KlineStorageCheck(
                KlineStorageCheckCode.COLLECTION,
                KlineStorageCheckStatus.FAILED,
                "K-line storage evidence collection failed.",
            ),
        ),
        evidence=None,
        error_type=_safe_error_type(error_type),
        sensitive_values=tuple(sensitive_values),
    )


def get_kline_storage_overview(
    bind: Engine | Connection,
    *,
    now: datetime | None = None,
    cache: KlineStorageOverviewCache | None = None,
) -> KlineStorageOverview:
    """Return a cached overview without running the full capacity preflight."""
    overview_cache = cache or _kline_storage_overview_cache
    return overview_cache.get(bind, now=now)


def invalidate_kline_storage_overview_cache(bind: Engine | Connection | None = None) -> None:
    """Invalidate one database binding or the complete process-local overview cache."""
    _kline_storage_overview_cache.invalidate(bind)


def collect_kline_storage_overview(
    bind: Engine | Connection,
    *,
    now: datetime | None = None,
) -> KlineStorageOverview:
    """Collect request-safe aggregate storage metadata with dialect-specific queries."""
    dialect = bind.dialect.name.casefold()
    if dialect == "postgresql":
        return _collect_postgresql_overview(bind, now)
    if dialect == "sqlite":
        return _collect_sqlite_overview(bind, now)
    raise UnsupportedKlineStorageDialectError


def _collect_postgresql_overview(
    bind: Engine | Connection,
    now: datetime | None,
) -> KlineStorageOverview:
    with _storage_connection(bind) as connection:
        relation_row = (
            connection.execute(
                text(
                    """
                    /* kline_storage:overview_relation */
                    WITH RECURSIVE relation_tree AS (
                        SELECT relation.oid, relation.relkind, relation.reltuples
                        FROM pg_class AS relation
                        WHERE relation.oid = to_regclass('kline_data')
                        UNION ALL
                        SELECT child.oid, child.relkind, child.reltuples
                        FROM pg_inherits AS inheritance
                        JOIN relation_tree AS parent
                          ON inheritance.inhparent = parent.oid
                        JOIN pg_class AS child
                          ON child.oid = inheritance.inhrelid
                    )
                    SELECT
                        bool_or(
                            relation_tree.oid = to_regclass('kline_data')
                            AND relation_tree.relkind = 'p'
                        ) AS is_partitioned,
                        CAST(
                            SUM(
                                CASE
                                    WHEN relation_tree.relkind = 'p' THEN 0
                                    ELSE GREATEST(
                                        COALESCE(table_stats.n_live_tup, 0),
                                        COALESCE(relation_tree.reltuples, 0),
                                        0
                                    )
                                END
                            )
                            AS BIGINT
                        ) AS row_estimate,
                        CAST(SUM(pg_table_size(relation_tree.oid)) AS BIGINT) AS table_bytes,
                        CAST(SUM(pg_indexes_size(relation_tree.oid)) AS BIGINT) AS index_bytes,
                        CAST(SUM(pg_total_relation_size(relation_tree.oid)) AS BIGINT) AS total_bytes
                    FROM relation_tree
                    LEFT JOIN pg_stat_all_tables AS table_stats
                      ON table_stats.relid = relation_tree.oid
                    """
                )
            )
            .mappings()
            .first()
        )
        if relation_row is None or relation_row["row_estimate"] is None:
            raise KlineStorageCollectionError

        is_partitioned = bool(relation_row["is_partitioned"])
        partition_rows = []
        if is_partitioned:
            partition_rows = (
                connection.execute(
                    text(
                        """
                        /* kline_storage:overview_partition_tree */
                        WITH RECURSIVE partition_tree AS (
                            SELECT inheritance.inhrelid AS relation_id
                            FROM pg_inherits AS inheritance
                            WHERE inheritance.inhparent = to_regclass('kline_data')
                            UNION ALL
                            SELECT inheritance.inhrelid
                            FROM pg_inherits AS inheritance
                            JOIN partition_tree AS parent
                              ON inheritance.inhparent = parent.relation_id
                        )
                        SELECT
                            child.relname AS partition_name,
                            pg_get_expr(child.relpartbound, child.oid, true) AS partition_bound
                        FROM partition_tree
                        JOIN pg_class AS child
                          ON child.oid = partition_tree.relation_id
                        ORDER BY child.relname
                        """
                    )
                )
                .mappings()
                .all()
            )
        last_collection_time = _collect_last_kline_collection_time(connection)

    required_months = _future_months(now)
    missing_months = _missing_future_months(required_months, partition_rows) if is_partitioned else required_months
    return KlineStorageOverview(
        dialect="postgresql",
        storage_bytes=KlineStorageBytes(
            table=int(relation_row["table_bytes"]),
            indexes=int(relation_row["index_bytes"]),
            total=int(relation_row["total_bytes"]),
        ),
        row_estimate=int(relation_row["row_estimate"]),
        row_count=None,
        partitioning_supported=True,
        is_partitioned=is_partitioned,
        partition_count=len(partition_rows),
        required_future_months=required_months,
        missing_future_months=missing_months,
        last_collection_time=last_collection_time,
        collected_at=_format_generated_at(now),
    )


def _collect_sqlite_overview(
    bind: Engine | Connection,
    now: datetime | None,
) -> KlineStorageOverview:
    with _storage_connection(bind) as connection:
        row_count = connection.execute(
            text("/* kline_storage:overview_sqlite_count */ SELECT COUNT(*) FROM kline_data")
        ).scalar_one()
        last_collection_time = _collect_last_kline_collection_time(connection)

    return KlineStorageOverview(
        dialect="sqlite",
        storage_bytes=KlineStorageBytes(table=None, indexes=None, total=None),
        row_estimate=None,
        row_count=int(row_count),
        partitioning_supported=False,
        is_partitioned=False,
        partition_count=0,
        required_future_months=(),
        missing_future_months=(),
        last_collection_time=last_collection_time,
        collected_at=_format_generated_at(now),
    )


def _collect_last_kline_collection_time(connection: Connection) -> str | None:
    value = connection.execute(
        text(
            """
            /* kline_storage:overview_last_collection */
            SELECT MAX(COALESCE(finished_at, started_at))
            FROM data_ingestion_runs
            WHERE job_name LIKE :job_pattern
              AND status = :success_status
            """
        ),
        {
            "job_pattern": "sync_kline_%",
            "success_status": "success",
        },
    ).scalar_one()
    return _format_database_time(value)


@contextmanager
def _storage_connection(bind: Engine | Connection) -> Iterator[Connection]:
    if isinstance(bind, Connection):
        yield bind
        return
    with bind.connect() as connection:
        yield connection


def run_kline_storage_preflight(
    engine: Engine,
    *,
    minute_query_p99_ms: float | None = None,
    trace_id: str | None = None,
    now: datetime | None = None,
    sensitive_values: Sequence[str] = (),
) -> KlineStorageReport:
    """Collect read-only capacity evidence and evaluate partition thresholds."""
    effective_trace_id = trace_id or uuid.uuid4().hex
    try:
        _validate_p99(minute_query_p99_ms)
        dialect = engine.dialect.name.casefold()
        if dialect == "postgresql":
            evidence = _collect_postgresql(engine, minute_query_p99_ms, now)
        elif dialect == "sqlite":
            evidence = _collect_sqlite(engine, minute_query_p99_ms, now)
        else:
            raise UnsupportedKlineStorageDialectError
    except Exception as exc:
        return build_kline_storage_failure_report(
            type(exc).__name__,
            trace_id=effective_trace_id,
            now=now,
            sensitive_values=sensitive_values,
        )

    status, checks, trigger_codes = _evaluate_evidence(evidence)
    return KlineStorageReport(
        trace_id=effective_trace_id,
        generated_at=_format_generated_at(now),
        status=status,
        checks=checks,
        evidence=evidence,
        trigger_codes=trigger_codes,
        sensitive_values=tuple(sensitive_values),
    )


class UnsupportedKlineStorageDialectError(RuntimeError):
    """Raised when no read-only collector exists for a database dialect."""


class InvalidMinuteQueryP99Error(ValueError):
    """Raised when an external P99 value is invalid."""


class KlineStorageCollectionError(RuntimeError):
    """Raised when required aggregate evidence is absent."""


def _collect_postgresql(
    engine: Engine,
    minute_query_p99_ms: float | None,
    now: datetime | None,
) -> KlineStorageEvidence:
    with engine.connect() as connection:
        version = connection.execute(
            text("/* kline_storage:postgres_version */ SELECT current_setting('server_version') AS database_version")
        ).scalar_one()
        size_row = (
            connection.execute(
                text(
                    """
                    /* kline_storage:postgres_sizes */
                    SELECT
                        pg_table_size('kline_data'::regclass) AS table_bytes,
                        pg_indexes_size('kline_data'::regclass) AS index_bytes,
                        pg_total_relation_size('kline_data'::regclass) AS total_bytes
                    """
                )
            )
            .mappings()
            .one()
        )
        period_rows = (
            connection.execute(
                text(
                    """
                    /* kline_storage:period_stats */
                    SELECT
                        period,
                        COUNT(*) AS row_count,
                        MIN(trading_time) AS min_trading_time,
                        MAX(trading_time) AS max_trading_time
                    FROM kline_data
                    GROUP BY period
                    ORDER BY period
                    """
                )
            )
            .mappings()
            .all()
        )
        partition_row = (
            connection.execute(
                text(
                    """
                    /* kline_storage:partition_state */
                    SELECT c.relkind = 'p' AS is_partitioned
                    FROM pg_class AS c
                    WHERE c.oid = to_regclass('kline_data')
                    """
                )
            )
            .mappings()
            .first()
        )
        if partition_row is None:
            raise KlineStorageCollectionError
        partition_rows = (
            connection.execute(
                text(
                    """
                    /* kline_storage:partition_tree */
                    WITH RECURSIVE partition_tree AS (
                        SELECT inheritance.inhrelid AS relation_id
                        FROM pg_inherits AS inheritance
                        WHERE inheritance.inhparent = to_regclass('kline_data')
                        UNION ALL
                        SELECT inheritance.inhrelid
                        FROM pg_inherits AS inheritance
                        JOIN partition_tree AS parent
                          ON inheritance.inhparent = parent.relation_id
                    )
                    SELECT
                        child.relname AS partition_name,
                        pg_get_expr(child.relpartbound, child.oid, true) AS partition_bound
                    FROM partition_tree
                    JOIN pg_class AS child ON child.oid = partition_tree.relation_id
                    ORDER BY child.relname
                    """
                )
            )
            .mappings()
            .all()
        )
        plans = _collect_postgresql_plans(connection, now)

    periods = _period_stats(period_rows)
    required_months = _future_months(now)
    is_partitioned = bool(partition_row["is_partitioned"])
    missing_months = _missing_future_months(required_months, partition_rows) if is_partitioned else required_months
    return KlineStorageEvidence(
        dialect="postgresql",
        database_version=str(version),
        row_count=sum(period.row_count for period in periods),
        row_count_kind="exact_grouped_count",
        storage_bytes=KlineStorageBytes(
            table=int(size_row["table_bytes"]),
            indexes=int(size_row["index_bytes"]),
            total=int(size_row["total_bytes"]),
        ),
        periods=periods,
        partitioning=KlinePartitionState(
            supported=True,
            is_partitioned=is_partitioned,
            partition_count=len(partition_rows),
            required_future_months=required_months,
            missing_future_months=missing_months,
        ),
        minute_query_p99_ms=minute_query_p99_ms,
        minute_query_plans=plans,
    )


def _collect_sqlite(
    engine: Engine,
    minute_query_p99_ms: float | None,
    now: datetime | None,
) -> KlineStorageEvidence:
    with engine.connect() as connection:
        version = connection.execute(text("/* kline_storage:sqlite_version */ SELECT sqlite_version()")).scalar_one()
        period_rows = (
            connection.execute(
                text(
                    """
                    /* kline_storage:period_stats */
                    SELECT
                        period,
                        COUNT(*) AS row_count,
                        MIN(trading_time) AS min_trading_time,
                        MAX(trading_time) AS max_trading_time
                    FROM kline_data
                    GROUP BY period
                    ORDER BY period
                    """
                )
            )
            .mappings()
            .all()
        )

    periods = _period_stats(period_rows)
    return KlineStorageEvidence(
        dialect="sqlite",
        database_version=str(version),
        row_count=sum(period.row_count for period in periods),
        row_count_kind="exact_grouped_count",
        storage_bytes=KlineStorageBytes(table=None, indexes=None, total=None),
        periods=periods,
        partitioning=KlinePartitionState(
            supported=False,
            is_partitioned=False,
            partition_count=0,
            required_future_months=_future_months(now),
            missing_future_months=(),
        ),
        minute_query_p99_ms=minute_query_p99_ms,
        minute_query_plans=(),
    )


def _collect_postgresql_plans(
    connection: Connection,
    now: datetime | None,
) -> tuple[KlineQueryPlanSummary, ...]:
    end_time = now or datetime.now(UTC)
    if end_time.tzinfo is None:
        end_time = end_time.replace(tzinfo=UTC)
    start_time = end_time - timedelta(days=7)
    common_parameters = {
        "period": "1m",
        "start_time": start_time,
        "end_time": end_time,
        "query_limit": 1000,
    }
    query_specs = (
        (
            "KLINE_VARIETY_MINUTE_RANGE",
            """
            /* kline_storage:explain_variety_minute */
            EXPLAIN (FORMAT JSON, VERBOSE FALSE, COSTS TRUE)
            SELECT *
            FROM kline_data
            WHERE variety_id = :entity_id
              AND period = :period
              AND trading_time >= :start_time
              AND trading_time <= :end_time
            ORDER BY trading_time DESC
            LIMIT :query_limit
            """,
            0,
        ),
        (
            "KLINE_CONTRACT_MINUTE_RANGE",
            """
            /* kline_storage:explain_contract_minute */
            EXPLAIN (FORMAT JSON, VERBOSE FALSE, COSTS TRUE)
            SELECT *
            FROM kline_data
            WHERE contract_id = :entity_id
              AND period = :period
              AND trading_time >= :start_time
              AND trading_time <= :end_time
            ORDER BY trading_time DESC
            LIMIT :query_limit
            """,
            0,
        ),
    )
    summaries = []
    for query_code, statement, entity_id in query_specs:
        parameters = {**common_parameters, "entity_id": entity_id}
        raw_plan = connection.execute(text(statement), parameters).scalar_one()
        summaries.append(_summarize_postgresql_plan(query_code, raw_plan))
    return tuple(summaries)


def _summarize_postgresql_plan(query_code: str, raw_plan: Any) -> KlineQueryPlanSummary:
    parsed = json.loads(raw_plan) if isinstance(raw_plan, str) else raw_plan
    document = parsed[0] if isinstance(parsed, list) else parsed
    if not isinstance(document, Mapping) or not isinstance(document.get("Plan"), Mapping):
        raise KlineStorageCollectionError
    root = document["Plan"]

    node_types: Counter[str] = Counter()
    relation_names: set[str] = set()
    index_names: set[str] = set()
    subplans_removed = 0
    stack = [root]
    while stack:
        node = stack.pop()
        node_type = node.get("Node Type")
        if isinstance(node_type, str):
            node_types[node_type] += 1
        relation_name = node.get("Relation Name")
        if isinstance(relation_name, str):
            relation_names.add(relation_name)
        index_name = node.get("Index Name")
        if isinstance(index_name, str):
            index_names.add(index_name)
        subplans_removed += _optional_int(node.get("Subplans Removed")) or 0
        children = node.get("Plans", ())
        if isinstance(children, list):
            stack.extend(child for child in children if isinstance(child, Mapping))

    return KlineQueryPlanSummary(
        query_code=query_code,
        root_node_type=str(root.get("Node Type", "Unknown")),
        node_type_counts=dict(sorted(node_types.items())),
        relation_names=tuple(sorted(relation_names)),
        index_names=tuple(sorted(index_names)),
        startup_cost=_optional_float(root.get("Startup Cost")),
        total_cost=_optional_float(root.get("Total Cost")),
        plan_rows=_optional_int(root.get("Plan Rows")),
        subplans_removed=subplans_removed,
        planning_time_ms=_optional_float(document.get("Planning Time")),
    )


def _evaluate_evidence(
    evidence: KlineStorageEvidence,
) -> tuple[
    KlineStorageStatus,
    tuple[KlineStorageCheck, ...],
    tuple[KlineStorageCheckCode, ...],
]:
    if evidence.dialect == "sqlite":
        return _evaluate_sqlite(evidence)

    row_triggered = evidence.row_count >= KLINE_ROW_COUNT_THRESHOLD
    total_bytes = evidence.storage_bytes.total
    bytes_triggered = total_bytes is not None and total_bytes >= KLINE_TOTAL_BYTES_THRESHOLD
    p99 = evidence.minute_query_p99_ms
    p99_triggered = p99 is not None and p99 >= KLINE_MINUTE_QUERY_P99_THRESHOLD_MS
    trigger_codes = tuple(
        code
        for triggered, code in (
            (row_triggered, KlineStorageCheckCode.ROW_COUNT_THRESHOLD),
            (bytes_triggered, KlineStorageCheckCode.TOTAL_BYTES_THRESHOLD),
            (p99_triggered, KlineStorageCheckCode.MINUTE_QUERY_P99_THRESHOLD),
        )
        if triggered
    )

    missing_months = evidence.partitioning.missing_future_months
    checks = (
        KlineStorageCheck(
            KlineStorageCheckCode.COLLECTION,
            KlineStorageCheckStatus.PASSED,
            "K-line storage evidence was collected with read-only queries.",
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.DATABASE_DIALECT,
            KlineStorageCheckStatus.PASSED,
            "PostgreSQL partitioning evidence is supported.",
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.DATABASE_VERSION,
            KlineStorageCheckStatus.PASSED,
            "Database version was collected.",
        ),
        _threshold_check(
            KlineStorageCheckCode.ROW_COUNT_THRESHOLD,
            row_triggered,
            "K-line row count reached the partition threshold.",
            "K-line row count is below the partition threshold.",
        ),
        _threshold_check(
            KlineStorageCheckCode.TOTAL_BYTES_THRESHOLD,
            bytes_triggered,
            "K-line total bytes reached the partition threshold.",
            "K-line total bytes are below the partition threshold.",
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.PERIOD_DISTRIBUTION,
            KlineStorageCheckStatus.PASSED,
            "Period counts and time bounds were collected.",
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.PARTITION_STATE,
            KlineStorageCheckStatus.PASSED,
            "PostgreSQL partition state was collected.",
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.FUTURE_MONTH_COVERAGE,
            (
                KlineStorageCheckStatus.WARNING
                if evidence.partitioning.is_partitioned and missing_months
                else (
                    KlineStorageCheckStatus.PASSED
                    if evidence.partitioning.is_partitioned
                    else KlineStorageCheckStatus.NOT_APPLICABLE
                )
            ),
            (
                "One or more required future minute partition months are missing."
                if evidence.partitioning.is_partitioned and missing_months
                else (
                    "Required future minute partition months are covered."
                    if evidence.partitioning.is_partitioned
                    else "Future month coverage is not applicable to an unpartitioned table."
                )
            ),
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.MINUTE_QUERY_PLAN,
            (KlineStorageCheckStatus.PASSED if evidence.minute_query_plans else KlineStorageCheckStatus.NOT_AVAILABLE),
            (
                "Core minute query EXPLAIN summaries were collected without ANALYZE."
                if evidence.minute_query_plans
                else "Core minute query EXPLAIN summaries were unavailable."
            ),
        ),
        (
            _threshold_check(
                KlineStorageCheckCode.MINUTE_QUERY_P99_THRESHOLD,
                p99_triggered,
                "Minute query P99 reached the partition threshold.",
                "Minute query P99 is below the partition threshold.",
            )
            if p99 is not None
            else KlineStorageCheck(
                KlineStorageCheckCode.MINUTE_QUERY_P99_THRESHOLD,
                KlineStorageCheckStatus.NOT_AVAILABLE,
                "Minute query P99 was not supplied by an external read-only benchmark.",
            )
        ),
    )

    if trigger_codes:
        status = KlineStorageStatus.RECOMMENDED
    elif p99 is None:
        status = KlineStorageStatus.INCONCLUSIVE
    else:
        status = KlineStorageStatus.NOT_REQUIRED
    return status, checks, trigger_codes


def _evaluate_sqlite(
    evidence: KlineStorageEvidence,
) -> tuple[
    KlineStorageStatus,
    tuple[KlineStorageCheck, ...],
    tuple[KlineStorageCheckCode, ...],
]:
    row_triggered = evidence.row_count >= KLINE_ROW_COUNT_THRESHOLD
    trigger_codes = (KlineStorageCheckCode.ROW_COUNT_THRESHOLD,) if row_triggered else ()
    checks = (
        KlineStorageCheck(
            KlineStorageCheckCode.COLLECTION,
            KlineStorageCheckStatus.PASSED,
            "SQLite K-line aggregate evidence was collected with read-only queries.",
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.DATABASE_DIALECT,
            KlineStorageCheckStatus.UNSUPPORTED,
            "SQLite is unsupported for PostgreSQL partitioning.",
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.DATABASE_VERSION,
            KlineStorageCheckStatus.PASSED,
            "Database version was collected.",
        ),
        _threshold_check(
            KlineStorageCheckCode.ROW_COUNT_THRESHOLD,
            row_triggered,
            "K-line row count reached the capacity threshold.",
            "K-line row count is below the capacity threshold.",
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.TOTAL_BYTES_THRESHOLD,
            KlineStorageCheckStatus.UNSUPPORTED,
            "PostgreSQL relation byte statistics are unavailable on SQLite.",
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.PERIOD_DISTRIBUTION,
            KlineStorageCheckStatus.PASSED,
            "Period counts and time bounds were collected.",
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.PARTITION_STATE,
            KlineStorageCheckStatus.UNSUPPORTED,
            "Partition state is unsupported on SQLite.",
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.FUTURE_MONTH_COVERAGE,
            KlineStorageCheckStatus.UNSUPPORTED,
            "Future partition coverage is unsupported on SQLite.",
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.MINUTE_QUERY_PLAN,
            KlineStorageCheckStatus.UNSUPPORTED,
            "PostgreSQL EXPLAIN evidence is unsupported on SQLite.",
        ),
        KlineStorageCheck(
            KlineStorageCheckCode.MINUTE_QUERY_P99_THRESHOLD,
            KlineStorageCheckStatus.NOT_AVAILABLE,
            "Minute query P99 is not used for a SQLite partitioning conclusion.",
        ),
    )
    return KlineStorageStatus.UNSUPPORTED_FOR_PARTITIONING, checks, trigger_codes


def _threshold_check(
    code: KlineStorageCheckCode,
    triggered: bool,
    triggered_summary: str,
    passed_summary: str,
) -> KlineStorageCheck:
    return KlineStorageCheck(
        code,
        KlineStorageCheckStatus.TRIGGERED if triggered else KlineStorageCheckStatus.PASSED,
        triggered_summary if triggered else passed_summary,
    )


def _period_stats(rows: Sequence[Mapping[str, Any]]) -> tuple[KlinePeriodStats, ...]:
    return tuple(
        KlinePeriodStats(
            period=str(row["period"]),
            row_count=int(row["row_count"]),
            min_trading_time=_format_database_time(row["min_trading_time"]),
            max_trading_time=_format_database_time(row["max_trading_time"]),
        )
        for row in rows
    )


def _future_months(now: datetime | None) -> tuple[str, ...]:
    current = now or datetime.now(UTC)
    month_start = date(current.year, current.month, 1)
    return tuple(_add_months(month_start, offset).strftime("%Y-%m") for offset in range(1, KLINE_FUTURE_MONTHS + 1))


def _missing_future_months(
    required_months: tuple[str, ...],
    partition_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    ranges = []
    for row in partition_rows:
        bound = row.get("partition_bound")
        if not isinstance(bound, str):
            continue
        match = _PARTITION_RANGE_PATTERN.search(bound)
        if match is None:
            continue
        lower = _parse_partition_bound(match.group(1))
        upper = _parse_partition_bound(match.group(2))
        if lower is not None and upper is not None:
            ranges.append((lower, upper))

    missing = []
    for label in required_months:
        month_start = date.fromisoformat(f"{label}-01")
        month_end = _add_months(month_start, 1)
        if not any(lower <= month_start and upper >= month_end for lower, upper in ranges):
            missing.append(label)
    return tuple(missing)


def _parse_partition_bound(value: str) -> date | None:
    candidate = value.strip().replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(candidate).date()
    except ValueError:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None


def _add_months(value: date, offset: int) -> date:
    month_index = value.year * 12 + value.month - 1 + offset
    return date(month_index // 12, month_index % 12 + 1, 1)


def _format_database_time(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return normalized.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _format_generated_at(value: datetime | None) -> str:
    generated_at = value or datetime.now(UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    return generated_at.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validate_p99(value: float | None) -> None:
    if value is not None and (not math.isfinite(value) or value < 0):
        raise InvalidMinuteQueryP99Error


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _safe_error_type(value: str) -> str:
    return value if _SAFE_ERROR_TYPE_PATTERN.fullmatch(value) else "DatabaseError"


def _redact_json_value(value: Any, sensitive_values: Sequence[str]) -> Any:
    if isinstance(value, str):
        return redact_sensitive_text(value, sensitive_values)
    if isinstance(value, list):
        return [_redact_json_value(item, sensitive_values) for item in value]
    if isinstance(value, tuple):
        return [_redact_json_value(item, sensitive_values) for item in value]
    if isinstance(value, Mapping):
        return {key: _redact_json_value(item, sensitive_values) for key, item in value.items()}
    return value
