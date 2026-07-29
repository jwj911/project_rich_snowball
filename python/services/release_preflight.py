"""只读的生产发布预检核心能力。"""

from __future__ import annotations

import ipaddress
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit


class CheckCode(StrEnum):
    """稳定的生产发布预检代码。"""

    ENV_PRODUCTION = "ENV_PRODUCTION"
    DATABASE_POSTGRESQL = "DATABASE_POSTGRESQL"
    SECRET_KEY_STRONG = "SECRET_KEY_STRONG"
    CORS_ORIGINS_SECURE = "CORS_ORIGINS_SECURE"
    DATA_SOURCE_REAL = "DATA_SOURCE_REAL"
    REDIS_URL_CONFIGURED = "REDIS_URL_CONFIGURED"
    RELEASE_COMMIT_PRESENT = "RELEASE_COMMIT_PRESENT"
    RELEASE_WINDOW_UTC = "RELEASE_WINDOW_UTC"
    RELEASE_OWNER_PRESENT = "RELEASE_OWNER_PRESENT"
    ROLLBACK_OWNER_PRESENT = "ROLLBACK_OWNER_PRESENT"
    SSE_DEPLOYMENT_MODE_SUPPORTED = "SSE_DEPLOYMENT_MODE_SUPPORTED"


class CheckStatus(StrEnum):
    """单项检查状态。"""

    PASSED = "passed"
    FAILED = "failed"


class PreflightStatus(StrEnum):
    """预检总状态。"""

    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class ReleasePreflightInput:
    """生产配置和发布元数据的只读快照。"""

    environment: str | None = None
    database_url: str | None = None
    secret_key: str | None = None
    cors_origins: str | None = None
    data_source: str | None = None
    redis_url: str | None = None
    release_commit: str | None = None
    release_window_utc: str | None = None
    release_owner: str | None = None
    rollback_owner: str | None = None
    sse_deployment_mode: str | None = None
    sensitive_values: tuple[str, ...] = field(default=(), repr=False, compare=False)

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> ReleasePreflightInput:
        """从环境变量风格的映射创建输入快照。"""
        cors_origins = _first_non_empty(values.get("CORS_ORIGINS"), values.get("ALLOW_ORIGINS"))
        return cls(
            environment=_optional_string(values.get("ENV")),
            database_url=_optional_string(values.get("DATABASE_URL")),
            secret_key=_optional_string(values.get("SECRET_KEY")),
            cors_origins=cors_origins,
            data_source=_optional_string(values.get("DATA_SOURCE")),
            redis_url=_optional_string(values.get("REDIS_URL")),
            release_commit=_optional_string(values.get("RELEASE_COMMIT")),
            release_window_utc=_optional_string(values.get("RELEASE_WINDOW_UTC")),
            release_owner=_optional_string(values.get("RELEASE_OWNER")),
            rollback_owner=_optional_string(values.get("ROLLBACK_OWNER")),
            sse_deployment_mode=_optional_string(values.get("SSE_DEPLOYMENT_MODE")),
            sensitive_values=_collect_sensitive_values(values),
        )


@dataclass(frozen=True)
class CheckResult:
    """单项预检结果。"""

    code: CheckCode
    status: CheckStatus
    summary: str

    def to_dict(self) -> dict[str, str]:
        """转换为稳定的 JSON 结构。"""
        return {
            "code": self.code.value,
            "status": self.status.value,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class PreflightReport:
    """一次生产发布预检的结构化报告。"""

    trace_id: str
    generated_at: str
    status: PreflightStatus
    checks: tuple[CheckResult, ...]
    metadata: Mapping[str, str | None]
    schema_version: int = 1

    @property
    def passed(self) -> bool:
        """全部门禁是否通过。"""
        return self.status is PreflightStatus.PASSED

    def to_dict(self) -> dict[str, Any]:
        """转换为可审计的稳定 JSON 结构。"""
        passed_count = sum(check.status is CheckStatus.PASSED for check in self.checks)
        return {
            "schema_version": self.schema_version,
            "trace_id": self.trace_id,
            "generated_at": self.generated_at,
            "status": self.status.value,
            "metadata": dict(self.metadata),
            "summary": {
                "total": len(self.checks),
                "passed": passed_count,
                "failed": len(self.checks) - passed_count,
            },
            "checks": [check.to_dict() for check in self.checks],
        }

    def to_json(self) -> str:
        """序列化为适合文件和命令输出的 JSON。"""
        return json.dumps(self.to_dict(), ensure_ascii=True, indent=2)


_URL_CREDENTIALS_PATTERN = re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)([^/\s@]+)@")
_NAMED_SECRET_PATTERN = re.compile(
    r"(?i)\b([a-z0-9_.-]*(?:password|passwd|secret(?:_key)?|api[_-]?key|token))"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_SENSITIVE_KEY_MARKERS = ("SECRET", "TOKEN", "PASSWORD", "PASSWD", "API_KEY", "DATABASE_URL", "REDIS_URL")
_SUPPORTED_SSE_MODES = frozenset({"single", "sticky"})


def redact_sensitive_text(value: object, sensitive_values: Sequence[str] = ()) -> str:
    """统一清除文本中的已知密钥、Provider Token 和 URL 凭据。"""
    redacted = str(value)
    for secret in sorted({item for item in sensitive_values if item}, key=len, reverse=True):
        redacted = redacted.replace(secret, "***")
    redacted = _URL_CREDENTIALS_PATTERN.sub(r"\1***@", redacted)
    return _NAMED_SECRET_PATTERN.sub(lambda match: f"{match.group(1)}{match.group(2)}***", redacted)


def normalize_release_window_utc(value: str | None) -> str | None:
    """校验并规范化 UTC 时间点或 ``start/end`` 发布窗口。"""
    if not value or not value.strip():
        return None

    parts = [part.strip() for part in value.split("/")]
    if len(parts) not in (1, 2) or any(not part for part in parts):
        return None

    try:
        timestamps = [_parse_utc_datetime(part) for part in parts]
    except ValueError:
        return None

    if len(timestamps) == 2 and timestamps[0] >= timestamps[1]:
        return None
    return "/".join(_format_utc_datetime(timestamp) for timestamp in timestamps)


def run_release_preflight(
    preflight_input: ReleasePreflightInput | Mapping[str, Any],
    *,
    trace_id: str | None = None,
    now: datetime | None = None,
) -> PreflightReport:
    """执行无副作用的生产发布预检。"""
    inputs = (
        preflight_input
        if isinstance(preflight_input, ReleasePreflightInput)
        else ReleasePreflightInput.from_mapping(preflight_input)
    )
    normalized_window = normalize_release_window_utc(inputs.release_window_utc)
    sensitive_values = _effective_sensitive_values(inputs)
    checks = (
        _result(
            inputs.environment is not None and inputs.environment.strip() == "production",
            CheckCode.ENV_PRODUCTION,
            "ENV is production.",
            "ENV must be production.",
        ),
        _result(
            _is_postgresql_url(inputs.database_url),
            CheckCode.DATABASE_POSTGRESQL,
            "PostgreSQL database URL is configured.",
            "DATABASE_URL must use PostgreSQL.",
        ),
        _result(
            inputs.secret_key is not None and len(inputs.secret_key) >= 32,
            CheckCode.SECRET_KEY_STRONG,
            "SECRET_KEY meets the minimum length.",
            "SECRET_KEY must contain at least 32 characters.",
        ),
        _result(
            _are_secure_cors_origins(inputs.cors_origins),
            CheckCode.CORS_ORIGINS_SECURE,
            "CORS origins are explicit HTTPS origins.",
            "CORS origins must use HTTPS and exclude wildcards, localhost, and loopback hosts.",
        ),
        _result(
            bool(inputs.data_source and inputs.data_source.strip()) and inputs.data_source.strip().casefold() != "mock",
            CheckCode.DATA_SOURCE_REAL,
            "A non-mock DATA_SOURCE is configured.",
            "DATA_SOURCE must be explicit and cannot be mock.",
        ),
        _result(
            bool(inputs.redis_url and inputs.redis_url.strip()),
            CheckCode.REDIS_URL_CONFIGURED,
            "REDIS_URL is configured.",
            "REDIS_URL must be configured.",
        ),
        _result(
            bool(inputs.release_commit and inputs.release_commit.strip()),
            CheckCode.RELEASE_COMMIT_PRESENT,
            "Release commit is present.",
            "Release commit is required.",
        ),
        _result(
            normalized_window is not None,
            CheckCode.RELEASE_WINDOW_UTC,
            "UTC release window is valid.",
            "Release window must be an explicit UTC timestamp or UTC start/end interval.",
        ),
        _result(
            bool(inputs.release_owner and inputs.release_owner.strip()),
            CheckCode.RELEASE_OWNER_PRESENT,
            "Release owner is present.",
            "Release owner is required.",
        ),
        _result(
            bool(inputs.rollback_owner and inputs.rollback_owner.strip()),
            CheckCode.ROLLBACK_OWNER_PRESENT,
            "Rollback owner is present.",
            "Rollback owner is required.",
        ),
        _result(
            bool(inputs.sse_deployment_mode) and inputs.sse_deployment_mode.strip().casefold() in _SUPPORTED_SSE_MODES,
            CheckCode.SSE_DEPLOYMENT_MODE_SUPPORTED,
            "SSE deployment mode is supported.",
            "SSE_DEPLOYMENT_MODE must be single or sticky; cross-instance connection registration is not implemented.",
        ),
    )
    status = (
        PreflightStatus.PASSED
        if all(check.status is CheckStatus.PASSED for check in checks)
        else PreflightStatus.FAILED
    )
    generated_at = now or datetime.now(UTC)
    if generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)

    return PreflightReport(
        trace_id=trace_id or uuid.uuid4().hex,
        generated_at=_format_utc_datetime(generated_at),
        status=status,
        checks=checks,
        metadata={
            "release_commit": _safe_metadata(inputs.release_commit, sensitive_values),
            "release_window_utc": normalized_window,
        },
    )


def _result(condition: bool, code: CheckCode, passed_summary: str, failed_summary: str) -> CheckResult:
    return CheckResult(
        code=code,
        status=CheckStatus.PASSED if condition else CheckStatus.FAILED,
        summary=passed_summary if condition else failed_summary,
    )


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _first_non_empty(*values: Any) -> str | None:
    for value in values:
        if value is not None and str(value).strip():
            return str(value)
    return None


def _is_sensitive_key(key: str) -> bool:
    normalized = key.upper()
    return any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def _collect_sensitive_values(values: Mapping[str, Any]) -> tuple[str, ...]:
    sensitive_values: list[str] = []
    for key, value in values.items():
        if value is None or not str(value) or not _is_sensitive_key(str(key)):
            continue
        raw_value = str(value)
        sensitive_values.append(raw_value)
        if str(key).upper() in {"DATABASE_URL", "REDIS_URL"}:
            sensitive_values.extend(_url_password_values(raw_value))
    return tuple(dict.fromkeys(sensitive_values))


def _effective_sensitive_values(inputs: ReleasePreflightInput) -> tuple[str, ...]:
    sensitive_values = list(inputs.sensitive_values)
    for value in (inputs.secret_key, inputs.database_url, inputs.redis_url):
        if value:
            sensitive_values.append(value)
    for value in (inputs.database_url, inputs.redis_url):
        if value:
            sensitive_values.extend(_url_password_values(value))
    return tuple(dict.fromkeys(sensitive_values))


def _url_password_values(value: str) -> tuple[str, ...]:
    try:
        password = urlsplit(value).password
    except ValueError:
        return ()
    return (password,) if password else ()


def _safe_metadata(value: str | None, sensitive_values: Sequence[str]) -> str | None:
    if value is None:
        return None
    return redact_sensitive_text(value.strip(), sensitive_values)


def _is_postgresql_url(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    try:
        scheme = urlsplit(value.strip()).scheme.casefold()
    except ValueError:
        return False
    return scheme in {"postgres", "postgresql"} or scheme.startswith("postgresql+")


def _are_secure_cors_origins(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    origins = [origin.strip() for origin in value.split(",") if origin.strip()]
    return bool(origins) and all(_is_secure_cors_origin(origin) for origin in origins)


def _is_secure_cors_origin(origin: str) -> bool:
    if "*" in origin:
        return False
    try:
        parsed = urlsplit(origin)
        host = (parsed.hostname or "").rstrip(".").casefold()
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme.casefold() != "https"
        or not host
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        return False
    if port is not None and not 1 <= port <= 65535:
        return False
    if host == "localhost" or host.endswith(".localhost") or host.startswith("127."):
        return False
    try:
        return not ipaddress.ip_address(host).is_loopback
    except ValueError:
        return True


def _parse_utc_datetime(value: str) -> datetime:
    candidate = value.strip()
    if candidate.upper().endswith(" UTC"):
        candidate = f"{candidate[:-4]}+00:00"
    elif candidate.upper().endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    parsed = datetime.fromisoformat(candidate)
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("timestamp is not UTC")
    return parsed.astimezone(UTC)


def _format_utc_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
