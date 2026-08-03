"""Bounded, read-only CSP evidence classification and readiness reporting."""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
import uuid
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, select, text
from sqlalchemy.engine import Connection, Engine

CSP_EVIDENCE_INPUT_MAX_BYTES = 64 * 1024
CSP_EVIDENCE_REPORT_MAX_BYTES = 256 * 1024
CSP_EVIDENCE_WINDOW_MAX_DAYS = 31
CSP_EVIDENCE_ROW_LIMIT = 50_000
CSP_EVIDENCE_PAGE_SIZE = 500
CSP_EVIDENCE_GROUP_LIMIT = 500
CSP_EVIDENCE_CATALOG_LIMIT = 500
CSP_EVIDENCE_ORIGIN_LIMIT = 20
CSP_EVIDENCE_RUNTIME_SECONDS = 30
CSP_EVIDENCE_STATEMENT_TIMEOUT_MS = 30_000
R9_CSP_PAYLOAD_MAX_BYTES = 8 * 1024


class EvidenceSource(StrEnum):
    """Controlled source of an evidence window."""

    SYNTHETIC = "synthetic"
    TARGET_ENVIRONMENT = "target_environment"


class EvidenceEnvironment(StrEnum):
    """Controlled deployment environments."""

    DEVELOPMENT = "development"
    CI = "ci"
    STAGING = "staging"
    PRODUCTION = "production"


class WorkflowName(StrEnum):
    """Fixed workflow matrix required for readiness."""

    LOGIN = "login"
    REFRESH_RECOVERY = "refresh_recovery"
    CONCURRENT_401_SINGLEFLIGHT = "concurrent_401_singleflight"
    LOGOUT = "logout"
    SSE_INITIAL_CONNECT = "sse_initial_connect"
    SSE_RECONNECT = "sse_reconnect"
    PRODUCTS = "products"
    PRODUCT_DETAIL = "product_detail"
    WORKSPACE = "workspace"
    STRATEGIES = "strategies"
    AGENTS = "agents"
    BEARER_WRITE = "bearer_write"
    COOKIE_ONLY_WRITE_REJECTED = "cookie_only_write_rejected"
    CSP_REPORTING_CANARY = "csp_reporting_canary"


class WorkflowStatus(StrEnum):
    """Controlled workflow result."""

    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


class RouteCategory(StrEnum):
    """Low-cardinality application route categories."""

    HOME = "home"
    PRODUCTS = "products"
    PRODUCT_DETAIL = "product_detail"
    WORKSPACE = "workspace"
    MY_COMMENTS = "my_comments"
    AGENTS = "agents"
    AGENT_DETAIL = "agent_detail"
    CHAT = "chat"
    STRATEGIES = "strategies"
    STRATEGY_EVOLUTION = "strategy_evolution"
    ALERTS = "alerts"
    NEWS = "news"
    OPINIONS = "opinions"
    PORTFOLIO = "portfolio"
    METRICS = "metrics"
    SETTINGS = "settings"
    UNKNOWN = "unknown"


class DirectiveCategory(StrEnum):
    """Low-cardinality CSP directive categories."""

    SCRIPT_SRC = "script_src"
    SCRIPT_SRC_ELEM = "script_src_elem"
    SCRIPT_SRC_ATTR = "script_src_attr"
    STYLE_SRC = "style_src"
    STYLE_SRC_ELEM = "style_src_elem"
    STYLE_SRC_ATTR = "style_src_attr"
    CONNECT_SRC = "connect_src"
    IMG_SRC = "img_src"
    FONT_SRC = "font_src"
    FRAME_SRC = "frame_src"
    WORKER_SRC = "worker_src"
    DEFAULT_SRC = "default_src"
    BASE_URI = "base_uri"
    FORM_ACTION = "form_action"
    OBJECT_SRC = "object_src"
    FRAME_ANCESTORS = "frame_ancestors"
    MANIFEST_SRC = "manifest_src"
    MEDIA_SRC = "media_src"
    CHILD_SRC = "child_src"
    UNKNOWN = "unknown"


class BlockedSourceCategory(StrEnum):
    """Fixed blocked source categories."""

    INLINE = "inline"
    EVAL = "eval"
    DATA = "data"
    BLOB = "blob"
    BROWSER_EXTENSION = "browser_extension"
    SAME_ORIGIN = "same_origin"
    TRUSTED_SOURCE = "trusted_source"
    EXTERNAL_UNTRUSTED = "external_untrusted"
    UNKNOWN = "unknown"


class CatalogDecision(StrEnum):
    """Controlled disposition for a catalogued violation."""

    REMEDIATE_BEFORE_S2 = "remediate_before_s2"
    MIGRATE_NONCE_IN_S2 = "migrate_nonce_in_s2"
    MIGRATE_HASH_IN_S2 = "migrate_hash_in_s2"
    REMOVE_SOURCE_IN_S2 = "remove_source_in_s2"
    NOT_APPLICABLE = "not_applicable"


class RetestStatus(StrEnum):
    """Controlled retest state."""

    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"
    NOT_APPLICABLE = "not_applicable"


class CspEvidenceStatus(StrEnum):
    """Overall evidence conclusion, ordered by evaluation priority."""

    FAILED = "failed"
    BLOCKED = "blocked"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    READY_FOR_REVIEW = "ready_for_review"


class CspEvidenceCheckStatus(StrEnum):
    """Status of one stable report check."""

    PASSED = "passed"
    FAILED = "failed"


class CspEvidenceCheckCode(StrEnum):
    """Stable, non-sensitive report check codes."""

    CONTEXT_VALID = "CSP_CONTEXT_VALID"
    CATALOG_VALID = "CSP_CATALOG_VALID"
    DATABASE_READ_ONLY = "CSP_DATABASE_READ_ONLY"
    QUERY_COMPLETE = "CSP_QUERY_COMPLETE"
    RECORD_INTEGRITY = "CSP_RECORD_INTEGRITY"
    METRICS_CONSISTENT = "CSP_METRICS_CONSISTENT"
    CATALOG_CLOSED = "CSP_CATALOG_CLOSED"
    EVIDENCE_COMPLETE = "CSP_EVIDENCE_COMPLETE"
    REPORT_BOUNDED = "CSP_REPORT_BOUNDED"


class CspEvidenceProblemCode(StrEnum):
    """Stable problem codes; values never include source data."""

    QUERY_FAILED = "CSP_QUERY_FAILED"
    REPORT_SIZE_EXCEEDED = "CSP_REPORT_SIZE_EXCEEDED"
    ROW_LIMIT_EXCEEDED = "CSP_ROW_LIMIT_EXCEEDED"
    GROUP_LIMIT_EXCEEDED = "CSP_GROUP_LIMIT_EXCEEDED"
    RUNTIME_LIMIT_EXCEEDED = "CSP_RUNTIME_LIMIT_EXCEEDED"
    PAYLOAD_TOO_LARGE = "CSP_PAYLOAD_TOO_LARGE"
    PAYLOAD_MALFORMED_JSON = "CSP_PAYLOAD_MALFORMED_JSON"
    PAYLOAD_NOT_OBJECT = "CSP_PAYLOAD_NOT_OBJECT"
    PAYLOAD_DUPLICATE_KEY = "CSP_PAYLOAD_DUPLICATE_KEY"
    PAYLOAD_EXTRA_KEY = "CSP_PAYLOAD_EXTRA_KEY"
    PAYLOAD_SENSITIVE_KEY = "CSP_PAYLOAD_SENSITIVE_KEY"
    PAYLOAD_TRACE_INVALID = "CSP_PAYLOAD_TRACE_INVALID"
    PAYLOAD_DOCUMENT_URL_INVALID = "CSP_PAYLOAD_DOCUMENT_URL_INVALID"
    PAYLOAD_DIRECTIVE_INVALID = "CSP_PAYLOAD_DIRECTIVE_INVALID"
    PAYLOAD_BLOCKED_URL_INVALID = "CSP_PAYLOAD_BLOCKED_URL_INVALID"
    PAYLOAD_OPTIONAL_URL_INVALID = "CSP_PAYLOAD_OPTIONAL_URL_INVALID"
    PAYLOAD_DISPOSITION_INVALID = "CSP_PAYLOAD_DISPOSITION_INVALID"
    PAYLOAD_NUMBER_INVALID = "CSP_PAYLOAD_NUMBER_INVALID"
    RECORD_SCOPE_MISMATCH = "CSP_RECORD_SCOPE_MISMATCH"
    UNEXPECTED_DOCUMENT_ORIGIN = "CSP_UNEXPECTED_DOCUMENT_ORIGIN"
    UNKNOWN_ROUTE_CATEGORY = "CSP_UNKNOWN_ROUTE_CATEGORY"
    UNKNOWN_DIRECTIVE_CATEGORY = "CSP_UNKNOWN_DIRECTIVE_CATEGORY"
    UNKNOWN_BLOCKED_SOURCE_CATEGORY = "CSP_UNKNOWN_BLOCKED_SOURCE_CATEGORY"
    UNKNOWN_VIOLATION = "CSP_UNKNOWN_VIOLATION"
    CATALOG_RETEST_PENDING = "CSP_CATALOG_RETEST_PENDING"
    CATALOG_RETEST_FAILED = "CSP_CATALOG_RETEST_FAILED"
    ACCEPTED_COUNT_MISMATCH = "CSP_ACCEPTED_COUNT_MISMATCH"
    PERSIST_FAILED = "CSP_PERSIST_FAILED"
    SYNTHETIC_EVIDENCE = "CSP_SYNTHETIC_EVIDENCE"
    NON_PRODUCTION_ENVIRONMENT = "CSP_NON_PRODUCTION_ENVIRONMENT"
    INCOMPLETE_BUSINESS_CYCLE = "CSP_INCOMPLETE_BUSINESS_CYCLE"
    WORKFLOW_NOT_PASSED = "CSP_WORKFLOW_NOT_PASSED"
    ZERO_SAMPLE_RATE = "CSP_ZERO_SAMPLE_RATE"
    MISSING_TRAFFIC_METRICS = "CSP_MISSING_TRAFFIC_METRICS"
    NO_TARGET_RECORDS = "CSP_NO_TARGET_RECORDS"
    UNSCOPED_RECORDS = "CSP_UNSCOPED_RECORDS"


class CspEvidenceInputCode(StrEnum):
    """Stable context and catalog validation failures."""

    CONTEXT_READ_FAILED = "CSP_CONTEXT_READ_FAILED"
    CONTEXT_TOO_LARGE = "CSP_CONTEXT_TOO_LARGE"
    CONTEXT_INVALID_UTF8 = "CSP_CONTEXT_INVALID_UTF8"
    CONTEXT_INVALID_JSON = "CSP_CONTEXT_INVALID_JSON"
    CONTEXT_INVALID_STRUCTURE = "CSP_CONTEXT_INVALID_STRUCTURE"
    CONTEXT_INVALID_SCHEMA_VERSION = "CSP_CONTEXT_INVALID_SCHEMA_VERSION"
    CONTEXT_INVALID_ENUM = "CSP_CONTEXT_INVALID_ENUM"
    CONTEXT_INVALID_RELEASE = "CSP_CONTEXT_INVALID_RELEASE"
    CONTEXT_INVALID_WINDOW = "CSP_CONTEXT_INVALID_WINDOW"
    CONTEXT_INVALID_SAMPLE_RATE = "CSP_CONTEXT_INVALID_SAMPLE_RATE"
    CONTEXT_INVALID_WORKFLOWS = "CSP_CONTEXT_INVALID_WORKFLOWS"
    CONTEXT_INVALID_METRICS = "CSP_CONTEXT_INVALID_METRICS"
    CONTEXT_INVALID_ORIGINS = "CSP_CONTEXT_INVALID_ORIGINS"
    CATALOG_READ_FAILED = "CSP_CATALOG_READ_FAILED"
    CATALOG_TOO_LARGE = "CSP_CATALOG_TOO_LARGE"
    CATALOG_INVALID_UTF8 = "CSP_CATALOG_INVALID_UTF8"
    CATALOG_INVALID_JSON = "CSP_CATALOG_INVALID_JSON"
    CATALOG_INVALID_STRUCTURE = "CSP_CATALOG_INVALID_STRUCTURE"
    CATALOG_INVALID_SCHEMA_VERSION = "CSP_CATALOG_INVALID_SCHEMA_VERSION"
    CATALOG_TOO_MANY_ENTRIES = "CSP_CATALOG_TOO_MANY_ENTRIES"
    CATALOG_INVALID_ENTRY = "CSP_CATALOG_INVALID_ENTRY"
    CATALOG_DUPLICATE_ID = "CSP_CATALOG_DUPLICATE_ID"
    CATALOG_DUPLICATE_CLASSIFICATION = "CSP_CATALOG_DUPLICATE_CLASSIFICATION"
    CATALOG_INVALID_RETEST_COMBINATION = "CSP_CATALOG_INVALID_RETEST_COMBINATION"


class CspEvidenceValidationError(ValueError):
    """Safe validation failure containing only a stable code."""

    def __init__(self, code: CspEvidenceInputCode):
        self.code = code
        super().__init__(code.value)


class CspEvidenceCollectionError(RuntimeError):
    """Raised for unsupported or malformed database query results."""


class CspEvidenceReportSizeError(RuntimeError):
    """Raised when a report cannot fit the fixed output bound."""


@dataclass(frozen=True)
class WorkflowResult:
    """One entry in the fixed workflow matrix."""

    name: WorkflowName
    status: WorkflowStatus


@dataclass(frozen=True)
class CspEvidenceMetrics:
    """Safe window counters supplied by the evidence operator."""

    business_http_requests: int
    received: int
    accepted: int
    sampled: int
    rejected: int
    rate_limited: int
    persist_failed: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "business_http_requests": self.business_http_requests,
            "csp_outcomes": {
                "received": self.received,
                "accepted": self.accepted,
                "sampled": self.sampled,
                "rejected": self.rejected,
                "rate_limited": self.rate_limited,
                "persist_failed": self.persist_failed,
            },
        }


@dataclass(frozen=True)
class CspEvidenceContext:
    """Validated, normalized evidence scope."""

    evidence_source: EvidenceSource
    environment: EvidenceEnvironment
    release: str
    window_start: datetime
    window_end: datetime
    sample_rate: float
    complete_business_cycle: bool
    workflows: tuple[WorkflowResult, ...]
    metrics: CspEvidenceMetrics
    expected_document_origins: tuple[str, ...]
    trusted_source_origins: tuple[str, ...]
    schema_version: int = 1

    def workflow_status(self, name: WorkflowName) -> WorkflowStatus:
        return next(item.status for item in self.workflows if item.name is name)


@dataclass(frozen=True)
class CatalogEntry:
    """One controlled known-violation catalog entry."""

    catalog_id: str
    route_category: RouteCategory
    directive_category: DirectiveCategory
    blocked_source_category: BlockedSourceCategory
    owner_role: str
    decision: CatalogDecision
    retest_status: RetestStatus

    @property
    def classification(self) -> tuple[RouteCategory, DirectiveCategory, BlockedSourceCategory]:
        return (
            self.route_category,
            self.directive_category,
            self.blocked_source_category,
        )


@dataclass(frozen=True)
class CspViolationCatalog:
    """Validated collection of unique known violations."""

    entries: tuple[CatalogEntry, ...]
    schema_version: int = 1

    def by_classification(
        self,
    ) -> dict[tuple[RouteCategory, DirectiveCategory, BlockedSourceCategory], CatalogEntry]:
        return {entry.classification: entry for entry in self.entries}


@dataclass(frozen=True, order=True)
class AggregateKey:
    """Fixed aggregation dimensions."""

    route_category: RouteCategory
    directive_category: DirectiveCategory
    blocked_source_category: BlockedSourceCategory


@dataclass(frozen=True)
class CspEvidenceAggregate:
    """Count for one fixed classification."""

    key: AggregateKey
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_category": self.key.route_category.value,
            "directive_category": self.key.directive_category.value,
            "blocked_source_category": self.key.blocked_source_category.value,
            "count": self.count,
        }


@dataclass(frozen=True)
class KnownViolation:
    """Low-sensitivity projection of an observed catalog match."""

    catalog_id: str
    key: AggregateKey
    owner_role: str
    decision: CatalogDecision
    retest_status: RetestStatus
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "catalog_id": self.catalog_id,
            "route_category": self.key.route_category.value,
            "directive_category": self.key.directive_category.value,
            "blocked_source_category": self.key.blocked_source_category.value,
            "owner_role": self.owner_role,
            "decision": self.decision.value,
            "retest_status": self.retest_status.value,
            "count": self.count,
        }


@dataclass(frozen=True)
class UnknownViolation:
    """Observed classification not closed by the catalog."""

    key: AggregateKey
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_category": self.key.route_category.value,
            "directive_category": self.key.directive_category.value,
            "blocked_source_category": self.key.blocked_source_category.value,
            "count": self.count,
        }


@dataclass(frozen=True)
class CspEvidenceProblem:
    """Stable problem count."""

    code: CspEvidenceProblemCode
    count: int

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code.value, "count": self.count}


@dataclass(frozen=True)
class CspEvidenceCheck:
    """Stable readiness check without free-form text."""

    code: CspEvidenceCheckCode
    status: CspEvidenceCheckStatus

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code.value, "status": self.status.value}


@dataclass(frozen=True)
class CspEvidenceCounts:
    """Safe counters collected during the bounded scan."""

    scanned_records: int = 0
    target_records: int = 0
    classified_records: int = 0
    known_records: int = 0
    unknown_records: int = 0
    invalid_records: int = 0
    unscoped_records: int = 0
    scope_mismatch_records: int = 0
    aggregate_groups: int = 0
    known_groups: int = 0
    unknown_groups: int = 0
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scanned_records": self.scanned_records,
            "target_records": self.target_records,
            "classified_records": self.classified_records,
            "known_records": self.known_records,
            "unknown_records": self.unknown_records,
            "invalid_records": self.invalid_records,
            "unscoped_records": self.unscoped_records,
            "scope_mismatch_records": self.scope_mismatch_records,
            "aggregate_groups": self.aggregate_groups,
            "known_groups": self.known_groups,
            "unknown_groups": self.unknown_groups,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class CspEvidenceRecord:
    """Only the database columns permitted in the evidence query."""

    id: int
    payload_json: str
    environment: str | None
    release: str | None
    created_at: datetime | None


@dataclass(frozen=True)
class CspEvidenceReport:
    """Deterministic, bounded CSP readiness report."""

    trace_id: str
    generated_at: str
    status: CspEvidenceStatus
    context: CspEvidenceContext
    counts: CspEvidenceCounts
    checks: tuple[CspEvidenceCheck, ...]
    problems: tuple[CspEvidenceProblem, ...]
    aggregates: tuple[CspEvidenceAggregate, ...]
    known_violations: tuple[KnownViolation, ...]
    unknown_violations: tuple[UnknownViolation, ...]
    metrics: CspEvidenceMetrics | None
    error_type: str | None = None
    schema_version: int = 1

    @property
    def ready_for_review(self) -> bool:
        return self.status is CspEvidenceStatus.READY_FOR_REVIEW

    def to_dict(self) -> dict[str, Any]:
        workflow_counts = Counter(item.status.value for item in self.context.workflows)
        return {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "generated_at": self.generated_at,
            "status": self.status.value,
            "scope": {
                "evidence_source": self.context.evidence_source.value,
                "environment": self.context.environment.value,
                "release": self.context.release,
                "window_start": _format_utc(self.context.window_start),
                "window_end": _format_utc(self.context.window_end),
                "sample_rate": self.context.sample_rate,
                "complete_business_cycle": self.context.complete_business_cycle,
            },
            "workflow_counts": dict(sorted(workflow_counts.items())),
            "metrics": self.metrics.to_dict() if self.metrics is not None else None,
            "counts": self.counts.to_dict(),
            "limits": {
                "input_bytes": CSP_EVIDENCE_INPUT_MAX_BYTES,
                "window_days": CSP_EVIDENCE_WINDOW_MAX_DAYS,
                "rows": CSP_EVIDENCE_ROW_LIMIT,
                "keyset_page": CSP_EVIDENCE_PAGE_SIZE,
                "aggregate_groups": CSP_EVIDENCE_GROUP_LIMIT,
                "catalog_entries": CSP_EVIDENCE_CATALOG_LIMIT,
                "origins_per_list": CSP_EVIDENCE_ORIGIN_LIMIT,
                "runtime_seconds": CSP_EVIDENCE_RUNTIME_SECONDS,
                "statement_timeout_ms": CSP_EVIDENCE_STATEMENT_TIMEOUT_MS,
                "report_bytes": CSP_EVIDENCE_REPORT_MAX_BYTES,
            },
            "checks": [check.to_dict() for check in self.checks],
            "problems": [problem.to_dict() for problem in self.problems],
            "aggregates": [aggregate.to_dict() for aggregate in self.aggregates],
            "known_violations": [violation.to_dict() for violation in self.known_violations],
            "unknown_violations": [violation.to_dict() for violation in self.unknown_violations],
            "error": (
                {
                    "code": self.problems[0].code.value,
                    "error_type": self.error_type,
                }
                if self.error_type and self.problems
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


_GIT_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_TRACE_ID_PATTERN = re.compile(r"^[0-9a-fA-F]{32}$")
_DIRECTIVE_PATTERN = re.compile(r"^[a-z0-9-]{1,64}$")
_SLUG_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9_-]{0,62}[A-Za-z0-9])?$")
_SAFE_ERROR_TYPE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,127}$")
_PRODUCT_DETAIL_PATTERN = re.compile(r"^/products/[^/]+$")
_DNS_LABEL_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

_CONTEXT_KEYS = frozenset(
    {
        "schema_version",
        "evidence_source",
        "environment",
        "release",
        "window_start",
        "window_end",
        "sample_rate",
        "complete_business_cycle",
        "workflows",
        "core_workflows",
        "metrics",
        "window_metrics",
        "expected_document_origins",
        "trusted_source_origins",
    }
)
_CATALOG_ENTRY_KEYS = frozenset(
    {
        "catalog_id",
        "route_category",
        "directive_category",
        "blocked_source_category",
        "owner_role",
        "decision",
        "retest_status",
    }
)
_R9_PAYLOAD_KEYS = frozenset(
    {
        "trace_id",
        "document_url",
        "blocked_url",
        "source_file",
        "referrer",
        "effective_directive",
        "violated_directive",
        "disposition",
        "line_number",
        "column_number",
        "status_code",
    }
)
_SENSITIVE_PAYLOAD_KEY_MARKERS = (
    "sample",
    "script",
    "dom",
    "cookie",
    "authorization",
    "credential",
    "token",
    "user_agent",
    "useragent",
    "user_id",
    "userid",
    "user",
    "url",
    "uri",
    "source",
    "path",
    "ua",
    "payload",
    "pathname",
)
_NOT_APPLICABLE_RETEST_DECISIONS = frozenset(
    {
        CatalogDecision.MIGRATE_NONCE_IN_S2,
        CatalogDecision.MIGRATE_HASH_IN_S2,
        CatalogDecision.REMOVE_SOURCE_IN_S2,
    }
)
_DIRECTIVE_CATEGORIES = {
    category.value.replace("_", "-"): category
    for category in DirectiveCategory
    if category is not DirectiveCategory.UNKNOWN
}
_ROUTE_CATEGORIES = {
    "/": RouteCategory.HOME,
    "/products": RouteCategory.PRODUCTS,
    "/workspace": RouteCategory.WORKSPACE,
    "/my-comments": RouteCategory.MY_COMMENTS,
    "/agents/detail": RouteCategory.AGENT_DETAIL,
    "/agents": RouteCategory.AGENTS,
    "/chat": RouteCategory.CHAT,
    "/strategies/evolution": RouteCategory.STRATEGY_EVOLUTION,
    "/strategies": RouteCategory.STRATEGIES,
    "/alerts": RouteCategory.ALERTS,
    "/news": RouteCategory.NEWS,
    "/opinions": RouteCategory.OPINIONS,
    "/portfolio": RouteCategory.PORTFOLIO,
    "/metrics": RouteCategory.METRICS,
    "/settings": RouteCategory.SETTINGS,
}
_BLOCKED_SOURCE_TOKENS = {
    "inline": BlockedSourceCategory.INLINE,
    "eval": BlockedSourceCategory.EVAL,
    "data": BlockedSourceCategory.DATA,
    "blob": BlockedSourceCategory.BLOB,
    "browser-extension": BlockedSourceCategory.BROWSER_EXTENSION,
}
_BLOCKING_PROBLEMS = frozenset(
    {
        CspEvidenceProblemCode.PAYLOAD_TOO_LARGE,
        CspEvidenceProblemCode.PAYLOAD_MALFORMED_JSON,
        CspEvidenceProblemCode.PAYLOAD_NOT_OBJECT,
        CspEvidenceProblemCode.PAYLOAD_DUPLICATE_KEY,
        CspEvidenceProblemCode.PAYLOAD_EXTRA_KEY,
        CspEvidenceProblemCode.PAYLOAD_SENSITIVE_KEY,
        CspEvidenceProblemCode.PAYLOAD_TRACE_INVALID,
        CspEvidenceProblemCode.PAYLOAD_DOCUMENT_URL_INVALID,
        CspEvidenceProblemCode.PAYLOAD_DIRECTIVE_INVALID,
        CspEvidenceProblemCode.PAYLOAD_BLOCKED_URL_INVALID,
        CspEvidenceProblemCode.PAYLOAD_OPTIONAL_URL_INVALID,
        CspEvidenceProblemCode.PAYLOAD_DISPOSITION_INVALID,
        CspEvidenceProblemCode.PAYLOAD_NUMBER_INVALID,
        CspEvidenceProblemCode.RECORD_SCOPE_MISMATCH,
        CspEvidenceProblemCode.UNEXPECTED_DOCUMENT_ORIGIN,
        CspEvidenceProblemCode.UNKNOWN_ROUTE_CATEGORY,
        CspEvidenceProblemCode.UNKNOWN_DIRECTIVE_CATEGORY,
        CspEvidenceProblemCode.UNKNOWN_BLOCKED_SOURCE_CATEGORY,
        CspEvidenceProblemCode.UNKNOWN_VIOLATION,
        CspEvidenceProblemCode.CATALOG_RETEST_PENDING,
        CspEvidenceProblemCode.CATALOG_RETEST_FAILED,
        CspEvidenceProblemCode.ACCEPTED_COUNT_MISMATCH,
        CspEvidenceProblemCode.PERSIST_FAILED,
    }
)
_INSUFFICIENT_PROBLEMS = frozenset(
    {
        CspEvidenceProblemCode.ROW_LIMIT_EXCEEDED,
        CspEvidenceProblemCode.GROUP_LIMIT_EXCEEDED,
        CspEvidenceProblemCode.RUNTIME_LIMIT_EXCEEDED,
        CspEvidenceProblemCode.SYNTHETIC_EVIDENCE,
        CspEvidenceProblemCode.NON_PRODUCTION_ENVIRONMENT,
        CspEvidenceProblemCode.INCOMPLETE_BUSINESS_CYCLE,
        CspEvidenceProblemCode.WORKFLOW_NOT_PASSED,
        CspEvidenceProblemCode.ZERO_SAMPLE_RATE,
        CspEvidenceProblemCode.MISSING_TRAFFIC_METRICS,
        CspEvidenceProblemCode.NO_TARGET_RECORDS,
        CspEvidenceProblemCode.UNSCOPED_RECORDS,
    }
)
_RECORD_INTEGRITY_PROBLEMS = frozenset(
    code
    for code in _BLOCKING_PROBLEMS
    if code.value.startswith("CSP_PAYLOAD_")
    or code
    in {
        CspEvidenceProblemCode.RECORD_SCOPE_MISMATCH,
        CspEvidenceProblemCode.UNEXPECTED_DOCUMENT_ORIGIN,
        CspEvidenceProblemCode.UNKNOWN_ROUTE_CATEGORY,
        CspEvidenceProblemCode.UNKNOWN_DIRECTIVE_CATEGORY,
        CspEvidenceProblemCode.UNKNOWN_BLOCKED_SOURCE_CATEGORY,
    }
)
_METRICS_PROBLEMS = frozenset(
    {
        CspEvidenceProblemCode.ACCEPTED_COUNT_MISMATCH,
        CspEvidenceProblemCode.PERSIST_FAILED,
        CspEvidenceProblemCode.MISSING_TRAFFIC_METRICS,
    }
)
_CATALOG_PROBLEMS = frozenset(
    {
        CspEvidenceProblemCode.UNKNOWN_VIOLATION,
        CspEvidenceProblemCode.CATALOG_RETEST_PENDING,
        CspEvidenceProblemCode.CATALOG_RETEST_FAILED,
    }
)

_metadata = MetaData()
_frontend_logs = Table(
    "frontend_logs",
    _metadata,
    Column("id", Integer),
    Column("type", String(20)),
    Column("payload_json", Text),
    Column("environment", String(20)),
    Column("release", String(50)),
    Column("created_at", DateTime(timezone=True)),
)


class _DuplicateJsonKeyError(ValueError):
    pass


@dataclass(frozen=True)
class _ParsedHttpUrl:
    origin: str
    path: str


@dataclass(frozen=True)
class _ValidatedPayload:
    key: AggregateKey | None
    problems: tuple[CspEvidenceProblemCode, ...]


def load_csp_evidence_context(path: str | os.PathLike[str]) -> CspEvidenceContext:
    """Load and validate a bounded UTF-8 context JSON file."""
    value = _load_json_file(
        path,
        read_code=CspEvidenceInputCode.CONTEXT_READ_FAILED,
        size_code=CspEvidenceInputCode.CONTEXT_TOO_LARGE,
        utf8_code=CspEvidenceInputCode.CONTEXT_INVALID_UTF8,
        json_code=CspEvidenceInputCode.CONTEXT_INVALID_JSON,
    )
    return validate_csp_evidence_context(value)


def validate_csp_evidence_context(value: object) -> CspEvidenceContext:
    """Validate and normalize an already parsed context document."""
    if not isinstance(value, Mapping):
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_STRUCTURE)
    keys = set(value)
    if not keys <= _CONTEXT_KEYS:
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_STRUCTURE)
    required = {
        "schema_version",
        "evidence_source",
        "environment",
        "release",
        "window_start",
        "window_end",
        "sample_rate",
        "complete_business_cycle",
        "expected_document_origins",
        "trusted_source_origins",
    }
    if not required <= keys:
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_STRUCTURE)
    if ("workflows" in value) == ("core_workflows" in value):
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_STRUCTURE)
    if ("metrics" in value) == ("window_metrics" in value):
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_STRUCTURE)
    if not _is_int(value["schema_version"]) or value["schema_version"] != 1:
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_SCHEMA_VERSION)

    try:
        evidence_source = EvidenceSource(value["evidence_source"])
        environment = EvidenceEnvironment(value["environment"])
    except (TypeError, ValueError):
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_ENUM)

    release = value["release"]
    if not isinstance(release, str) or _GIT_SHA_PATTERN.fullmatch(release) is None:
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_RELEASE)

    try:
        window_start = _parse_utc(value["window_start"])
        window_end = _parse_utc(value["window_end"])
    except (TypeError, ValueError):
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_WINDOW)
    if window_end <= window_start or window_end - window_start > timedelta(days=CSP_EVIDENCE_WINDOW_MAX_DAYS):
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_WINDOW)

    sample_rate = value["sample_rate"]
    if (
        isinstance(sample_rate, bool)
        or not isinstance(sample_rate, int | float)
        or not math.isfinite(float(sample_rate))
        or not 0 <= float(sample_rate) <= 1
    ):
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_SAMPLE_RATE)
    complete_business_cycle = value["complete_business_cycle"]
    if not isinstance(complete_business_cycle, bool):
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_STRUCTURE)

    workflow_value = value.get("workflows", value.get("core_workflows"))
    workflows = _validate_workflows(workflow_value)
    metric_value = value.get("metrics", value.get("window_metrics"))
    metrics = _validate_metrics(metric_value)
    expected_origins = _validate_origins(
        value["expected_document_origins"],
        production=environment is EvidenceEnvironment.PRODUCTION,
    )
    trusted_origins = _validate_origins(
        value["trusted_source_origins"],
        production=environment is EvidenceEnvironment.PRODUCTION,
    )

    return CspEvidenceContext(
        evidence_source=evidence_source,
        environment=environment,
        release=release,
        window_start=window_start,
        window_end=window_end,
        sample_rate=float(sample_rate),
        complete_business_cycle=complete_business_cycle,
        workflows=workflows,
        metrics=metrics,
        expected_document_origins=expected_origins,
        trusted_source_origins=trusted_origins,
    )


def load_csp_violation_catalog(path: str | os.PathLike[str]) -> CspViolationCatalog:
    """Load and validate a bounded UTF-8 violation catalog."""
    value = _load_json_file(
        path,
        read_code=CspEvidenceInputCode.CATALOG_READ_FAILED,
        size_code=CspEvidenceInputCode.CATALOG_TOO_LARGE,
        utf8_code=CspEvidenceInputCode.CATALOG_INVALID_UTF8,
        json_code=CspEvidenceInputCode.CATALOG_INVALID_JSON,
    )
    return validate_csp_violation_catalog(value)


def validate_csp_violation_catalog(value: object) -> CspViolationCatalog:
    """Validate and normalize an already parsed known-violation catalog."""
    if not isinstance(value, Mapping):
        _input_error(CspEvidenceInputCode.CATALOG_INVALID_STRUCTURE)
    entry_keys = [key for key in ("entries", "violations") if key in value]
    if set(value) - {"schema_version", "entries", "violations"} or len(entry_keys) != 1:
        _input_error(CspEvidenceInputCode.CATALOG_INVALID_STRUCTURE)
    if not _is_int(value.get("schema_version")) or value["schema_version"] != 1:
        _input_error(CspEvidenceInputCode.CATALOG_INVALID_SCHEMA_VERSION)
    raw_entries = value[entry_keys[0]]
    if not isinstance(raw_entries, list):
        _input_error(CspEvidenceInputCode.CATALOG_INVALID_STRUCTURE)
    if len(raw_entries) > CSP_EVIDENCE_CATALOG_LIMIT:
        _input_error(CspEvidenceInputCode.CATALOG_TOO_MANY_ENTRIES)

    entries: list[CatalogEntry] = []
    catalog_ids: set[str] = set()
    classifications: set[tuple[RouteCategory, DirectiveCategory, BlockedSourceCategory]] = set()
    for raw_entry in raw_entries:
        entry = _validate_catalog_entry(raw_entry)
        if entry.catalog_id in catalog_ids:
            _input_error(CspEvidenceInputCode.CATALOG_DUPLICATE_ID)
        if entry.classification in classifications:
            _input_error(CspEvidenceInputCode.CATALOG_DUPLICATE_CLASSIFICATION)
        catalog_ids.add(entry.catalog_id)
        classifications.add(entry.classification)
        entries.append(entry)
    entries.sort(key=lambda item: tuple(category.value for category in item.classification))
    return CspViolationCatalog(entries=tuple(entries))


def classify_route(path: str) -> RouteCategory:
    """Classify a URL path without retaining parameters."""
    if not isinstance(path, str) or not path.startswith("/"):
        return RouteCategory.UNKNOWN
    normalized = path if path == "/" else path.rstrip("/")
    if _PRODUCT_DETAIL_PATTERN.fullmatch(normalized):
        return RouteCategory.PRODUCT_DETAIL
    return _ROUTE_CATEGORIES.get(normalized, RouteCategory.UNKNOWN)


def classify_directive(value: str | None) -> DirectiveCategory:
    """Map one normalized R9 directive to a fixed category."""
    if not isinstance(value, str):
        return DirectiveCategory.UNKNOWN
    return _DIRECTIVE_CATEGORIES.get(value, DirectiveCategory.UNKNOWN)


def classify_blocked_source(
    blocked_url: str | None,
    document_url: str,
    trusted_source_origins: Sequence[str],
) -> BlockedSourceCategory:
    """Classify a blocked source without exposing its origin or path."""
    if not isinstance(blocked_url, str):
        return BlockedSourceCategory.UNKNOWN
    token_category = _BLOCKED_SOURCE_TOKENS.get(blocked_url)
    if token_category is not None:
        return token_category
    blocked = _parse_http_url(blocked_url)
    document = _parse_http_url(document_url)
    if blocked is None or document is None:
        return BlockedSourceCategory.UNKNOWN
    if blocked.origin == document.origin:
        return BlockedSourceCategory.SAME_ORIGIN
    if blocked.origin in trusted_source_origins:
        return BlockedSourceCategory.TRUSTED_SOURCE
    return BlockedSourceCategory.EXTERNAL_UNTRUSTED


def build_csp_evidence_failure_report(
    context: CspEvidenceContext,
    error_type: str,
    *,
    trace_id: str | None = None,
    now: datetime | None = None,
    problem_code: CspEvidenceProblemCode = CspEvidenceProblemCode.QUERY_FAILED,
) -> CspEvidenceReport:
    """Build a minimal failed report without retaining exception text."""
    return CspEvidenceReport(
        trace_id=_report_trace_id(trace_id),
        generated_at=_format_generated_at(now),
        status=CspEvidenceStatus.FAILED,
        context=context,
        counts=CspEvidenceCounts(),
        checks=(
            CspEvidenceCheck(
                CspEvidenceCheckCode.CONTEXT_VALID,
                CspEvidenceCheckStatus.PASSED,
            ),
            CspEvidenceCheck(
                CspEvidenceCheckCode.CATALOG_VALID,
                CspEvidenceCheckStatus.PASSED,
            ),
            CspEvidenceCheck(
                CspEvidenceCheckCode.DATABASE_READ_ONLY,
                CspEvidenceCheckStatus.FAILED,
            ),
            CspEvidenceCheck(
                CspEvidenceCheckCode.QUERY_COMPLETE,
                CspEvidenceCheckStatus.FAILED,
            ),
            CspEvidenceCheck(
                CspEvidenceCheckCode.RECORD_INTEGRITY,
                CspEvidenceCheckStatus.FAILED,
            ),
            CspEvidenceCheck(
                CspEvidenceCheckCode.METRICS_CONSISTENT,
                CspEvidenceCheckStatus.FAILED,
            ),
            CspEvidenceCheck(
                CspEvidenceCheckCode.CATALOG_CLOSED,
                CspEvidenceCheckStatus.FAILED,
            ),
            CspEvidenceCheck(
                CspEvidenceCheckCode.EVIDENCE_COMPLETE,
                CspEvidenceCheckStatus.FAILED,
            ),
            CspEvidenceCheck(
                CspEvidenceCheckCode.REPORT_BOUNDED,
                (
                    CspEvidenceCheckStatus.FAILED
                    if problem_code is CspEvidenceProblemCode.REPORT_SIZE_EXCEEDED
                    else CspEvidenceCheckStatus.PASSED
                ),
            ),
        ),
        problems=(CspEvidenceProblem(problem_code, 1),),
        aggregates=(),
        known_violations=(),
        unknown_violations=(),
        metrics=None,
        error_type=_safe_error_type(error_type),
    )


def run_csp_evidence(
    bind: Engine | Connection,
    context: CspEvidenceContext,
    catalog: CspViolationCatalog,
    *,
    trace_id: str | None = None,
    now: datetime | None = None,
    clock: Any = monotonic,
) -> CspEvidenceReport:
    """Collect bounded evidence, classify it, and evaluate readiness."""
    effective_trace_id = _report_trace_id(trace_id)
    try:
        report = _run_csp_evidence(
            bind,
            context,
            catalog,
            trace_id=effective_trace_id,
            now=now,
            clock=clock,
        )
        if len(report.to_json().encode("utf-8")) > CSP_EVIDENCE_REPORT_MAX_BYTES:
            raise CspEvidenceReportSizeError
        return report
    except CspEvidenceReportSizeError as exc:
        return build_csp_evidence_failure_report(
            context,
            type(exc).__name__,
            trace_id=effective_trace_id,
            now=now,
            problem_code=CspEvidenceProblemCode.REPORT_SIZE_EXCEEDED,
        )
    except Exception as exc:
        return build_csp_evidence_failure_report(
            context,
            type(exc).__name__,
            trace_id=effective_trace_id,
            now=now,
        )


def generate_csp_evidence_report(
    bind: Engine | Connection,
    context_path: str | os.PathLike[str],
    catalog_path: str | os.PathLike[str],
    *,
    trace_id: str | None = None,
    now: datetime | None = None,
    clock: Any = monotonic,
) -> CspEvidenceReport:
    """CLI-facing composition that validates both inputs before querying."""
    context = load_csp_evidence_context(context_path)
    catalog = load_csp_violation_catalog(catalog_path)
    return run_csp_evidence(
        bind,
        context,
        catalog,
        trace_id=trace_id,
        now=now,
        clock=clock,
    )


def _run_csp_evidence(
    bind: Engine | Connection,
    context: CspEvidenceContext,
    catalog: CspViolationCatalog,
    *,
    trace_id: str,
    now: datetime | None,
    clock: Any,
) -> CspEvidenceReport:
    started_at = clock()
    problems: Counter[CspEvidenceProblemCode] = Counter()
    aggregates: Counter[AggregateKey] = Counter()
    scanned_records = 0
    target_records = 0
    classified_records = 0
    invalid_records = 0
    unscoped_records = 0
    scope_mismatch_records = 0
    truncated = False
    last_id = 0

    _add_context_problems(context, problems)
    for entry in catalog.entries:
        if entry.retest_status is RetestStatus.PENDING:
            problems[CspEvidenceProblemCode.CATALOG_RETEST_PENDING] += 1
        elif entry.retest_status is RetestStatus.FAILED:
            problems[CspEvidenceProblemCode.CATALOG_RETEST_FAILED] += 1

    with _read_only_connection(bind) as connection:
        while True:
            if _runtime_exceeded(started_at, clock):
                problems[CspEvidenceProblemCode.RUNTIME_LIMIT_EXCEEDED] += 1
                truncated = True
                break
            page_limit = min(
                CSP_EVIDENCE_PAGE_SIZE,
                CSP_EVIDENCE_ROW_LIMIT - scanned_records + 1,
            )
            rows = _query_page(connection, context, last_id, page_limit=page_limit)
            if _runtime_exceeded(started_at, clock):
                problems[CspEvidenceProblemCode.RUNTIME_LIMIT_EXCEEDED] += 1
                truncated = True
                break
            if not rows:
                break

            stop_scan = False
            for row in rows:
                if scanned_records >= CSP_EVIDENCE_ROW_LIMIT:
                    problems[CspEvidenceProblemCode.ROW_LIMIT_EXCEEDED] += 1
                    truncated = True
                    stop_scan = True
                    break
                if _runtime_exceeded(started_at, clock):
                    problems[CspEvidenceProblemCode.RUNTIME_LIMIT_EXCEEDED] += 1
                    truncated = True
                    stop_scan = True
                    break

                record = _record_from_row(row)
                if record.id <= last_id:
                    raise CspEvidenceCollectionError
                last_id = record.id
                scanned_records += 1

                record_in_scope = True
                if not record.environment or not record.release:
                    unscoped_records += 1
                    problems[CspEvidenceProblemCode.UNSCOPED_RECORDS] += 1
                    record_in_scope = False
                elif record.environment != context.environment.value or record.release != context.release:
                    scope_mismatch_records += 1
                    problems[CspEvidenceProblemCode.RECORD_SCOPE_MISMATCH] += 1
                    record_in_scope = False
                else:
                    target_records += 1

                validated = _validate_payload(record.payload_json, context)
                for problem in validated.problems:
                    problems[problem] += 1
                if validated.key is None:
                    invalid_records += 1
                    continue
                if not record_in_scope:
                    continue

                if validated.key not in aggregates and len(aggregates) >= CSP_EVIDENCE_GROUP_LIMIT:
                    problems[CspEvidenceProblemCode.GROUP_LIMIT_EXCEEDED] += 1
                    truncated = True
                    stop_scan = True
                    break
                aggregates[validated.key] += 1
                classified_records += 1

            if stop_scan or len(rows) < CSP_EVIDENCE_PAGE_SIZE:
                break

    if target_records == 0:
        problems[CspEvidenceProblemCode.NO_TARGET_RECORDS] += 1
    if not truncated and _runtime_exceeded(started_at, clock):
        problems[CspEvidenceProblemCode.RUNTIME_LIMIT_EXCEEDED] += 1
        truncated = True
    if context.metrics.persist_failed > 0:
        problems[CspEvidenceProblemCode.PERSIST_FAILED] += context.metrics.persist_failed
    if not truncated and context.metrics.accepted != scanned_records:
        problems[CspEvidenceProblemCode.ACCEPTED_COUNT_MISMATCH] += 1

    aggregate_values = tuple(
        CspEvidenceAggregate(key=key, count=count)
        for key, count in sorted(aggregates.items(), key=lambda item: _aggregate_sort_key(item[0]))
    )
    known, unknown = _match_catalog(aggregate_values, catalog, problems)
    known_records = sum(item.count for item in known)
    unknown_records = sum(item.count for item in unknown)
    counts = CspEvidenceCounts(
        scanned_records=scanned_records,
        target_records=target_records,
        classified_records=classified_records,
        known_records=known_records,
        unknown_records=unknown_records,
        invalid_records=invalid_records,
        unscoped_records=unscoped_records,
        scope_mismatch_records=scope_mismatch_records,
        aggregate_groups=len(aggregate_values),
        known_groups=len(known),
        unknown_groups=len(unknown),
        truncated=truncated,
    )
    status = _evidence_status(problems)
    checks = _build_checks(problems, truncated)
    problem_values = tuple(
        CspEvidenceProblem(code=code, count=count)
        for code, count in sorted(problems.items(), key=lambda item: item[0].value)
        if count > 0
    )
    return CspEvidenceReport(
        trace_id=trace_id,
        generated_at=_format_generated_at(now),
        status=status,
        context=context,
        counts=counts,
        checks=checks,
        problems=problem_values,
        aggregates=aggregate_values,
        known_violations=known,
        unknown_violations=unknown,
        metrics=context.metrics,
    )


def _load_json_file(
    path: str | os.PathLike[str],
    *,
    read_code: CspEvidenceInputCode,
    size_code: CspEvidenceInputCode,
    utf8_code: CspEvidenceInputCode,
    json_code: CspEvidenceInputCode,
) -> object:
    try:
        with Path(path).open("rb") as file:
            payload = file.read(CSP_EVIDENCE_INPUT_MAX_BYTES + 1)
    except (OSError, TypeError, ValueError):
        _input_error(read_code)
    if len(payload) > CSP_EVIDENCE_INPUT_MAX_BYTES:
        _input_error(size_code)
    try:
        document = payload.decode("utf-8")
    except UnicodeDecodeError:
        _input_error(utf8_code)
    try:
        return json.loads(
            document,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, _DuplicateJsonKeyError, ValueError):
        _input_error(json_code)


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    value: dict[str, object] = {}
    for key, item in pairs:
        if key in value:
            raise _DuplicateJsonKeyError
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError


def _input_error(code: CspEvidenceInputCode) -> Any:
    raise CspEvidenceValidationError(code) from None


def _validate_workflows(value: object) -> tuple[WorkflowResult, ...]:
    if not isinstance(value, Mapping) or set(value) != {name.value for name in WorkflowName}:
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_WORKFLOWS)
    results = []
    for name in WorkflowName:
        try:
            status = WorkflowStatus(value[name.value])
        except (TypeError, ValueError):
            _input_error(CspEvidenceInputCode.CONTEXT_INVALID_WORKFLOWS)
        results.append(WorkflowResult(name=name, status=status))
    return tuple(results)


def _validate_metrics(value: object) -> CspEvidenceMetrics:
    if not isinstance(value, Mapping):
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_METRICS)
    business_aliases = (
        "business_http_requests",
        "business_http_request_count",
        "http_requests",
    )
    business_keys = [key for key in business_aliases if key in value]
    if len(business_keys) != 1:
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_METRICS)
    business_key = business_keys[0]

    if "csp_outcomes" in value:
        if set(value) != {business_key, "csp_outcomes"}:
            _input_error(CspEvidenceInputCode.CONTEXT_INVALID_METRICS)
        outcomes = value["csp_outcomes"]
        if not isinstance(outcomes, Mapping) or set(outcomes) != {
            "received",
            "accepted",
            "sampled",
            "rejected",
            "rate_limited",
            "persist_failed",
        }:
            _input_error(CspEvidenceInputCode.CONTEXT_INVALID_METRICS)
        normalized = dict(outcomes)
    else:
        aliases = {
            "received": ("received", "csp_reports_received"),
            "accepted": ("accepted", "csp_reports_accepted"),
            "sampled": ("sampled", "csp_reports_sampled"),
            "rejected": ("rejected", "csp_reports_rejected"),
            "rate_limited": ("rate_limited", "csp_reports_rate_limited"),
            "persist_failed": ("persist_failed", "csp_reports_persist_failed"),
        }
        normalized = {}
        consumed = {business_key}
        for canonical, options in aliases.items():
            present = [key for key in options if key in value]
            if len(present) != 1:
                _input_error(CspEvidenceInputCode.CONTEXT_INVALID_METRICS)
            normalized[canonical] = value[present[0]]
            consumed.add(present[0])
        if set(value) != consumed:
            _input_error(CspEvidenceInputCode.CONTEXT_INVALID_METRICS)

    metric_values = {"business_http_requests": value[business_key], **normalized}
    if any(not _is_int(item) or item < 0 for item in metric_values.values()):
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_METRICS)
    return CspEvidenceMetrics(**metric_values)


def _validate_origins(value: object, *, production: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > CSP_EVIDENCE_ORIGIN_LIMIT:
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_ORIGINS)
    origins = []
    for raw_origin in value:
        origin = _canonical_origin(raw_origin, production=production)
        if origin is None:
            _input_error(CspEvidenceInputCode.CONTEXT_INVALID_ORIGINS)
        origins.append(origin)
    if len(set(origins)) != len(origins):
        _input_error(CspEvidenceInputCode.CONTEXT_INVALID_ORIGINS)
    return tuple(origins)


def _validate_catalog_entry(value: object) -> CatalogEntry:
    if not isinstance(value, Mapping) or set(value) != _CATALOG_ENTRY_KEYS:
        _input_error(CspEvidenceInputCode.CATALOG_INVALID_ENTRY)
    catalog_id = value["catalog_id"]
    owner_role = value["owner_role"]
    if (
        not isinstance(catalog_id, str)
        or _SLUG_PATTERN.fullmatch(catalog_id) is None
        or not isinstance(owner_role, str)
        or _SLUG_PATTERN.fullmatch(owner_role) is None
    ):
        _input_error(CspEvidenceInputCode.CATALOG_INVALID_ENTRY)
    try:
        route = RouteCategory(value["route_category"])
        directive = DirectiveCategory(value["directive_category"])
        blocked_source = BlockedSourceCategory(value["blocked_source_category"])
        decision = CatalogDecision(value["decision"])
        retest = RetestStatus(value["retest_status"])
    except (TypeError, ValueError):
        _input_error(CspEvidenceInputCode.CATALOG_INVALID_ENTRY)
    if retest is RetestStatus.NOT_APPLICABLE and decision not in _NOT_APPLICABLE_RETEST_DECISIONS:
        _input_error(CspEvidenceInputCode.CATALOG_INVALID_RETEST_COMBINATION)
    return CatalogEntry(
        catalog_id=catalog_id,
        route_category=route,
        directive_category=directive,
        blocked_source_category=blocked_source,
        owner_role=owner_role,
        decision=decision,
        retest_status=retest,
    )


def _canonical_origin(value: object, *, production: bool = False) -> str | None:
    if not isinstance(value, str) or not value or len(value) > 500:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or any(character.isspace() or ord(character) < 32 for character in value)
    ):
        return None
    scheme = parsed.scheme.casefold()
    if production and scheme != "https":
        return None
    host = _canonical_host(parsed.hostname)
    if host is None:
        return None
    if port == (443 if scheme == "https" else 80):
        port = None
    return f"{scheme}://{host}{f':{port}' if port is not None else ''}"


def _canonical_host(value: str) -> str | None:
    if "%" in value:
        return None
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        try:
            host = value.rstrip(".").encode("idna").decode("ascii").casefold()
        except (UnicodeError, ValueError):
            return None
        if not host or len(host) > 253 or any(_DNS_LABEL_PATTERN.fullmatch(label) is None for label in host.split(".")):
            return None
        return host
    return f"[{address.compressed}]" if address.version == 6 else address.compressed


def _parse_http_url(value: object) -> _ParsedHttpUrl | None:
    if not isinstance(value, str) or not value or len(value) > 500:
        return None
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.casefold() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or len(parsed.path) > 300
    ):
        return None
    host = _canonical_host(parsed.hostname)
    if host is None:
        return None
    scheme = parsed.scheme.casefold()
    if port == (443 if scheme == "https" else 80):
        port = None
    origin = f"{scheme}://{host}{f':{port}' if port is not None else ''}"
    return _ParsedHttpUrl(origin=origin, path=parsed.path or "/")


def _validate_payload(payload_json: object, context: CspEvidenceContext) -> _ValidatedPayload:
    if not isinstance(payload_json, str):
        return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_MALFORMED_JSON)
    if len(payload_json.encode("utf-8")) > R9_CSP_PAYLOAD_MAX_BYTES:
        return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_TOO_LARGE)
    try:
        payload = json.loads(
            payload_json,
            object_pairs_hook=_unique_json_object,
            parse_constant=_reject_json_constant,
        )
    except _DuplicateJsonKeyError:
        return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_DUPLICATE_KEY)
    except (json.JSONDecodeError, UnicodeError, ValueError):
        return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_MALFORMED_JSON)
    if not isinstance(payload, Mapping):
        return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_NOT_OBJECT)

    extra_keys = set(payload) - _R9_PAYLOAD_KEYS
    if extra_keys:
        if any(_is_sensitive_payload_key(key) for key in extra_keys):
            return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_SENSITIVE_KEY)
        return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_EXTRA_KEY)

    trace_id = payload.get("trace_id")
    if not isinstance(trace_id, str) or _TRACE_ID_PATTERN.fullmatch(trace_id) is None:
        return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_TRACE_INVALID)
    document_url = payload.get("document_url")
    document = _parse_http_url(document_url)
    if document is None:
        return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_DOCUMENT_URL_INVALID)
    if document.origin not in context.expected_document_origins:
        return _invalid_payload(CspEvidenceProblemCode.UNEXPECTED_DOCUMENT_ORIGIN)

    effective = payload.get("effective_directive")
    violated = payload.get("violated_directive")
    if not _directive_field_valid(payload, "effective_directive") or not _directive_field_valid(
        payload,
        "violated_directive",
    ):
        return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_DIRECTIVE_INVALID)
    directive = effective or violated
    if not isinstance(directive, str):
        return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_DIRECTIVE_INVALID)
    if payload.get("disposition") != "report":
        return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_DISPOSITION_INVALID)

    for field in ("source_file", "referrer"):
        if field in payload and _parse_http_url(payload[field]) is None:
            return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_OPTIONAL_URL_INVALID)
    blocked_url = payload.get("blocked_url")
    if "blocked_url" in payload and (
        not isinstance(blocked_url, str)
        or (blocked_url not in _BLOCKED_SOURCE_TOKENS and _parse_http_url(blocked_url) is None)
    ):
        return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_BLOCKED_URL_INVALID)
    if not _payload_numbers_valid(payload):
        return _invalid_payload(CspEvidenceProblemCode.PAYLOAD_NUMBER_INVALID)

    route_category = classify_route(document.path)
    directive_category = classify_directive(directive)
    source_category = classify_blocked_source(
        blocked_url if isinstance(blocked_url, str) else None,
        document_url,
        context.trusted_source_origins,
    )
    problems = []
    if route_category is RouteCategory.UNKNOWN:
        problems.append(CspEvidenceProblemCode.UNKNOWN_ROUTE_CATEGORY)
    if directive_category is DirectiveCategory.UNKNOWN:
        problems.append(CspEvidenceProblemCode.UNKNOWN_DIRECTIVE_CATEGORY)
    if source_category is BlockedSourceCategory.UNKNOWN:
        problems.append(CspEvidenceProblemCode.UNKNOWN_BLOCKED_SOURCE_CATEGORY)
    return _ValidatedPayload(
        key=AggregateKey(route_category, directive_category, source_category),
        problems=tuple(problems),
    )


def _invalid_payload(problem: CspEvidenceProblemCode) -> _ValidatedPayload:
    return _ValidatedPayload(key=None, problems=(problem,))


def _is_sensitive_payload_key(key: object) -> bool:
    if not isinstance(key, str):
        return True
    normalized = key.casefold().replace("-", "_")
    return any(marker in normalized for marker in _SENSITIVE_PAYLOAD_KEY_MARKERS)


def _directive_field_valid(payload: Mapping[str, object], field: str) -> bool:
    if field not in payload:
        return True
    value = payload[field]
    return isinstance(value, str) and _DIRECTIVE_PATTERN.fullmatch(value) is not None


def _payload_numbers_valid(payload: Mapping[str, object]) -> bool:
    limits = {
        "line_number": 10_000_000,
        "column_number": 10_000_000,
        "status_code": 599,
    }
    for field, upper_bound in limits.items():
        if field not in payload:
            continue
        value = payload[field]
        if not _is_int(value) or not 0 <= value <= upper_bound:
            return False
    return True


@contextmanager
def _read_only_connection(bind: Engine | Connection) -> Iterator[Connection]:
    dialect = bind.dialect.name.casefold()
    if dialect not in {"postgresql", "sqlite"}:
        raise CspEvidenceCollectionError
    if isinstance(bind, Connection):
        yield from _configure_read_only_connection(bind, dialect)
        return
    with bind.connect() as connection:
        yield from _configure_read_only_connection(connection, dialect)


def _configure_read_only_connection(
    connection: Connection,
    dialect: str,
) -> Iterator[Connection]:
    if connection.in_transaction():
        raise CspEvidenceCollectionError

    if dialect == "postgresql":
        with connection.begin():
            connection.execute(text("SET TRANSACTION READ ONLY"))
            connection.execute(text(f"SET LOCAL statement_timeout = {CSP_EVIDENCE_STATEMENT_TIMEOUT_MS}"))
            yield connection
        return

    previous = int(connection.execute(text("PRAGMA query_only")).scalar_one())
    try:
        connection.execute(text("PRAGMA query_only=ON"))
        yield connection
    finally:
        if connection.in_transaction():
            connection.rollback()
        connection.execute(text(f"PRAGMA query_only={previous}"))
        if connection.in_transaction():
            connection.rollback()


def _query_page(
    connection: Connection,
    context: CspEvidenceContext,
    last_id: int,
    *,
    page_limit: int = CSP_EVIDENCE_PAGE_SIZE,
) -> list[Mapping[str, Any]]:
    statement = (
        select(
            _frontend_logs.c.id,
            _frontend_logs.c.payload_json,
            _frontend_logs.c.environment,
            _frontend_logs.c.release,
            _frontend_logs.c.created_at,
        )
        .where(
            _frontend_logs.c.type == "csp-violation",
            _frontend_logs.c.created_at >= context.window_start,
            _frontend_logs.c.created_at < context.window_end,
            _frontend_logs.c.id > last_id,
        )
        .order_by(_frontend_logs.c.id)
        .limit(page_limit)
    )
    return list(connection.execute(statement).mappings().all())


def _record_from_row(row: Mapping[str, Any]) -> CspEvidenceRecord:
    row_id = row.get("id")
    if not _is_int(row_id) or row_id <= 0:
        raise CspEvidenceCollectionError
    environment = row.get("environment")
    release = row.get("release")
    return CspEvidenceRecord(
        id=row_id,
        payload_json=row.get("payload_json"),
        environment=environment if isinstance(environment, str) else None,
        release=release if isinstance(release, str) else None,
        created_at=row.get("created_at"),
    )


def _add_context_problems(
    context: CspEvidenceContext,
    problems: Counter[CspEvidenceProblemCode],
) -> None:
    if context.evidence_source is EvidenceSource.SYNTHETIC:
        problems[CspEvidenceProblemCode.SYNTHETIC_EVIDENCE] += 1
    if context.environment is not EvidenceEnvironment.PRODUCTION:
        problems[CspEvidenceProblemCode.NON_PRODUCTION_ENVIRONMENT] += 1
    if not context.complete_business_cycle:
        problems[CspEvidenceProblemCode.INCOMPLETE_BUSINESS_CYCLE] += 1
    not_passed = sum(item.status is not WorkflowStatus.PASSED for item in context.workflows)
    if not_passed:
        problems[CspEvidenceProblemCode.WORKFLOW_NOT_PASSED] += not_passed
    if context.sample_rate == 0:
        problems[CspEvidenceProblemCode.ZERO_SAMPLE_RATE] += 1
    missing_metrics = sum(
        value == 0
        for value in (
            context.metrics.business_http_requests,
            context.metrics.received,
        )
    )
    if missing_metrics:
        problems[CspEvidenceProblemCode.MISSING_TRAFFIC_METRICS] += missing_metrics


def _match_catalog(
    aggregates: tuple[CspEvidenceAggregate, ...],
    catalog: CspViolationCatalog,
    problems: Counter[CspEvidenceProblemCode],
) -> tuple[tuple[KnownViolation, ...], tuple[UnknownViolation, ...]]:
    catalog_entries = catalog.by_classification()
    known = []
    unknown = []
    for aggregate in aggregates:
        entry = catalog_entries.get(
            (
                aggregate.key.route_category,
                aggregate.key.directive_category,
                aggregate.key.blocked_source_category,
            )
        )
        category_unknown = (
            aggregate.key.route_category is RouteCategory.UNKNOWN
            or aggregate.key.directive_category is DirectiveCategory.UNKNOWN
            or aggregate.key.blocked_source_category is BlockedSourceCategory.UNKNOWN
        )
        if entry is None or category_unknown:
            unknown.append(UnknownViolation(key=aggregate.key, count=aggregate.count))
            problems[CspEvidenceProblemCode.UNKNOWN_VIOLATION] += aggregate.count
            continue
        known.append(
            KnownViolation(
                catalog_id=entry.catalog_id,
                key=aggregate.key,
                owner_role=entry.owner_role,
                decision=entry.decision,
                retest_status=entry.retest_status,
                count=aggregate.count,
            )
        )
    return tuple(known), tuple(unknown)


def _evidence_status(
    problems: Counter[CspEvidenceProblemCode],
) -> CspEvidenceStatus:
    codes = {code for code, count in problems.items() if count > 0}
    if codes & _BLOCKING_PROBLEMS:
        return CspEvidenceStatus.BLOCKED
    if codes & _INSUFFICIENT_PROBLEMS:
        return CspEvidenceStatus.INSUFFICIENT_EVIDENCE
    return CspEvidenceStatus.READY_FOR_REVIEW


def _build_checks(
    problems: Counter[CspEvidenceProblemCode],
    truncated: bool,
) -> tuple[CspEvidenceCheck, ...]:
    active = {code for code, count in problems.items() if count > 0}
    incomplete = bool(active & _INSUFFICIENT_PROBLEMS)
    return (
        CspEvidenceCheck(
            CspEvidenceCheckCode.CONTEXT_VALID,
            CspEvidenceCheckStatus.PASSED,
        ),
        CspEvidenceCheck(
            CspEvidenceCheckCode.CATALOG_VALID,
            CspEvidenceCheckStatus.PASSED,
        ),
        CspEvidenceCheck(
            CspEvidenceCheckCode.DATABASE_READ_ONLY,
            CspEvidenceCheckStatus.PASSED,
        ),
        CspEvidenceCheck(
            CspEvidenceCheckCode.QUERY_COMPLETE,
            _check_status(not truncated),
        ),
        CspEvidenceCheck(
            CspEvidenceCheckCode.RECORD_INTEGRITY,
            _check_status(not bool(active & _RECORD_INTEGRITY_PROBLEMS)),
        ),
        CspEvidenceCheck(
            CspEvidenceCheckCode.METRICS_CONSISTENT,
            _check_status(not bool(active & _METRICS_PROBLEMS)),
        ),
        CspEvidenceCheck(
            CspEvidenceCheckCode.CATALOG_CLOSED,
            _check_status(not bool(active & _CATALOG_PROBLEMS)),
        ),
        CspEvidenceCheck(
            CspEvidenceCheckCode.EVIDENCE_COMPLETE,
            _check_status(not incomplete),
        ),
        CspEvidenceCheck(
            CspEvidenceCheckCode.REPORT_BOUNDED,
            CspEvidenceCheckStatus.PASSED,
        ),
    )


def _check_status(condition: bool) -> CspEvidenceCheckStatus:
    return CspEvidenceCheckStatus.PASSED if condition else CspEvidenceCheckStatus.FAILED


def _runtime_exceeded(started_at: float, clock: Any) -> bool:
    return clock() - started_at >= CSP_EVIDENCE_RUNTIME_SECONDS


def _aggregate_sort_key(key: AggregateKey) -> tuple[str, str, str]:
    return (
        key.route_category.value,
        key.directive_category.value,
        key.blocked_source_category.value,
    )


def _parse_utc(value: object) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError
    return parsed.astimezone(UTC)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _format_generated_at(value: datetime | None) -> str:
    generated_at = value or datetime.now(UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    return _format_utc(generated_at)


def _report_trace_id(value: str | None) -> str:
    if value is None:
        return uuid.uuid4().hex
    if _TRACE_ID_PATTERN.fullmatch(value) is None:
        raise ValueError
    return value.lower()


def _safe_error_type(value: str) -> str:
    return value if _SAFE_ERROR_TYPE_PATTERN.fullmatch(value) else "EvidenceError"


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


load_evidence_context = load_csp_evidence_context
load_violation_catalog = load_csp_violation_catalog
validate_evidence_context = validate_csp_evidence_context
validate_violation_catalog = validate_csp_violation_catalog
collect_csp_evidence = run_csp_evidence
CspBlockedSourceCategory = BlockedSourceCategory
CspCatalogDecision = CatalogDecision
CspCatalogEntry = CatalogEntry
CspDirectiveCategory = DirectiveCategory
CspEvidenceCatalog = CspViolationCatalog
CspRetestStatus = RetestStatus
CspRouteCategory = RouteCategory
load_csp_evidence_catalog = load_csp_violation_catalog

__all__ = [
    "AggregateKey",
    "BlockedSourceCategory",
    "CSP_EVIDENCE_CATALOG_LIMIT",
    "CSP_EVIDENCE_GROUP_LIMIT",
    "CSP_EVIDENCE_INPUT_MAX_BYTES",
    "CSP_EVIDENCE_ORIGIN_LIMIT",
    "CSP_EVIDENCE_PAGE_SIZE",
    "CSP_EVIDENCE_REPORT_MAX_BYTES",
    "CSP_EVIDENCE_ROW_LIMIT",
    "CSP_EVIDENCE_RUNTIME_SECONDS",
    "CSP_EVIDENCE_STATEMENT_TIMEOUT_MS",
    "CSP_EVIDENCE_WINDOW_MAX_DAYS",
    "CatalogDecision",
    "CatalogEntry",
    "CspBlockedSourceCategory",
    "CspCatalogDecision",
    "CspCatalogEntry",
    "CspDirectiveCategory",
    "CspEvidenceAggregate",
    "CspEvidenceCatalog",
    "CspEvidenceCheck",
    "CspEvidenceCheckCode",
    "CspEvidenceCheckStatus",
    "CspEvidenceCollectionError",
    "CspEvidenceContext",
    "CspEvidenceCounts",
    "CspEvidenceInputCode",
    "CspEvidenceMetrics",
    "CspEvidenceProblem",
    "CspEvidenceProblemCode",
    "CspEvidenceRecord",
    "CspEvidenceReport",
    "CspEvidenceReportSizeError",
    "CspEvidenceStatus",
    "CspEvidenceValidationError",
    "CspViolationCatalog",
    "CspRetestStatus",
    "CspRouteCategory",
    "DirectiveCategory",
    "EvidenceEnvironment",
    "EvidenceSource",
    "KnownViolation",
    "RetestStatus",
    "RouteCategory",
    "UnknownViolation",
    "WorkflowName",
    "WorkflowResult",
    "WorkflowStatus",
    "build_csp_evidence_failure_report",
    "classify_blocked_source",
    "classify_directive",
    "classify_route",
    "collect_csp_evidence",
    "generate_csp_evidence_report",
    "load_csp_evidence_context",
    "load_csp_evidence_catalog",
    "load_csp_violation_catalog",
    "load_evidence_context",
    "load_violation_catalog",
    "run_csp_evidence",
    "validate_csp_evidence_context",
    "validate_csp_violation_catalog",
    "validate_evidence_context",
    "validate_violation_catalog",
]
