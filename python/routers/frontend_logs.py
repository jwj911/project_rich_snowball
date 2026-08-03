"""前端监控日志端点。

接收 sentry-lite 和 web-vitals 的上报数据，写入 frontend_logs 表供后续查询和告警。
同时提供查询接口，支持 admin 全量查询和普通用户仅查询自己的日志。
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from config import CSP_REPORT_ENVIRONMENT, CSP_REPORT_SAMPLE_RATE, RELEASE_COMMIT
from dependencies import (
    get_current_user_dependency,
    get_db,
    get_optional_current_user,
)
from middleware.rate_limit import _get_client_ip, check_rate_limit
from models import FrontendLogDB, UserDB
from schemas import (
    CSPViolationReport,
    FrontendLogCreate,
    FrontendLogResponse,
    LegacyCSPReportEnvelope,
    ReportingAPICSPEnvelope,
)
from services.metrics import csp_reports_total

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/log", tags=["前端监控"])

# payload JSON 序列化后的最大字节数
_MAX_PAYLOAD_BYTES = 8 * 1024
_CSP_REPORT_MAX_BYTES = 8 * 1024
_CSP_REPORT_BATCH_MAX = 20
_CSP_REPORT_RATE_LIMIT_WINDOW_SECONDS = 60
_CSP_REPORT_RATE_LIMIT_MAX_REQUESTS = 60
_CSP_REPORT_RATE_LIMIT_ACTION = "report:csp"
_CSP_REPORT_CONTENT_TYPES = {
    "application/csp-report",
    "application/reports+json",
}
_CSP_BLOCKED_SOURCE_TOKENS = {
    "blob",
    "data",
    "eval",
    "inline",
}
_CSP_BROWSER_EXTENSION_SCHEMES = {
    "chrome-extension",
    "moz-extension",
}
_CSP_URL_MAX_LENGTH = 500
_CSP_URL_PATH_MAX_LENGTH = 300


def _payload_size_bytes(data: FrontendLogCreate) -> int:
    """估算 payload + meta 序列化后的字节数。"""
    try:
        return len(
            json.dumps(
                {"payload": data.payload, "meta": data.meta},
                ensure_ascii=False,
                default=str,
            ).encode("utf-8")
        )
    except (TypeError, ValueError):
        return 0


def _reject_csp_report(status_code: int, detail: str) -> None:
    csp_reports_total.labels(outcome="rejected").inc()
    raise HTTPException(status_code=status_code, detail=detail)


async def _read_bounded_csp_body(request: Request) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > _CSP_REPORT_MAX_BYTES:
                _reject_csp_report(413, "CSP report body exceeds 8 KiB")
        except ValueError:
            _reject_csp_report(400, "Invalid Content-Length")

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _CSP_REPORT_MAX_BYTES:
            _reject_csp_report(413, "CSP report body exceeds 8 KiB")
        body.extend(chunk)
    if not body:
        _reject_csp_report(400, "CSP report body is required")
    return bytes(body)


def _parse_csp_reports(content_type: str, payload: object) -> list[CSPViolationReport]:
    try:
        if content_type == "application/csp-report":
            return [LegacyCSPReportEnvelope.model_validate(payload).csp_report]

        if not isinstance(payload, list) or not 1 <= len(payload) <= _CSP_REPORT_BATCH_MAX:
            raise ValueError("invalid Reporting API batch")
        return [ReportingAPICSPEnvelope.model_validate(item).body for item in payload]
    except (TypeError, ValueError, ValidationError):
        _reject_csp_report(422, "Invalid CSP report structure")


def _sanitize_csp_http_url(value: str | None) -> str | None:
    if not value:
        return None

    compact_value = value.strip()
    try:
        parsed = urlsplit(compact_value)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            return None
        port = parsed.port
    except ValueError:
        return None

    hostname = parsed.hostname
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in hostname):
        return None
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:{port}" if port is not None else hostname
    scheme = parsed.scheme.casefold()
    base_url = urlunsplit((scheme, netloc, "", "", ""))
    if len(base_url) > _CSP_URL_MAX_LENGTH:
        return None

    path = "".join(character for character in parsed.path if ord(character) >= 32 and ord(character) != 127)
    path_limit = min(_CSP_URL_PATH_MAX_LENGTH, _CSP_URL_MAX_LENGTH - len(base_url))
    return urlunsplit((scheme, netloc, path[:path_limit], "", ""))


def _sanitize_csp_blocked_url(value: str | None) -> str | None:
    if not value:
        return None

    compact_value = value.strip()
    try:
        scheme = urlsplit(compact_value).scheme.casefold()
    except ValueError:
        return None
    if scheme in _CSP_BROWSER_EXTENSION_SCHEMES:
        return "browser-extension"

    token = compact_value.removesuffix(":").casefold()
    if token in _CSP_BLOCKED_SOURCE_TOKENS:
        return token
    return _sanitize_csp_http_url(compact_value)


def _normalize_csp_report(report: CSPViolationReport) -> dict[str, object]:
    document_url = _sanitize_csp_http_url(report.document_url)
    if document_url is None:
        _reject_csp_report(422, "Invalid CSP report URL")

    values: dict[str, object | None] = {
        "document_url": document_url,
        "blocked_url": _sanitize_csp_blocked_url(report.blocked_url),
        "source_file": _sanitize_csp_http_url(report.source_file),
        "referrer": _sanitize_csp_http_url(report.referrer),
        "effective_directive": report.effective_directive,
        "violated_directive": report.violated_directive,
        "disposition": report.disposition,
        "line_number": report.line_number,
        "column_number": report.column_number,
        "status_code": report.status_code,
    }
    return {key: value for key, value in values.items() if value is not None}


def _should_sample_csp_report(
    report: dict[str, object],
    *,
    sample_rate: float | None = None,
) -> bool:
    effective_rate = CSP_REPORT_SAMPLE_RATE if sample_rate is None else sample_rate
    if effective_rate <= 0:
        return False
    if effective_rate >= 1:
        return True

    canonical = json.dumps(
        report,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    bucket = int.from_bytes(hashlib.sha256(canonical).digest()[:8], "big") / 2**64
    return bucket < effective_rate


def _reject_non_finite_json_constant(value: str):
    raise ValueError("non-finite JSON constant")


def _persist_csp_reports(
    db: Session,
    prepared_reports: list[tuple[str, dict[str, object]]],
    *,
    trusted_environment: str | None = None,
    trusted_release: str | None = None,
) -> str | None:
    try:
        db.add_all(
            [
                FrontendLogDB(
                    user_id=None,
                    log_type="csp-violation",
                    level="warning",
                    url=str(normalized["document_url"]),
                    environment=trusted_environment,
                    release=trusted_release,
                    payload_json=json.dumps(
                        {"trace_id": trace_id, **normalized},
                        ensure_ascii=True,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                )
                for trace_id, normalized in prepared_reports
            ]
        )
        db.commit()
    except Exception as exc:
        error_type = type(exc).__name__
        try:
            db.rollback()
        except Exception as rollback_exc:
            logger.warning(
                "csp_report_rollback_failed",
                extra={
                    "trace_id": prepared_reports[0][0],
                    "error_type": type(rollback_exc).__name__,
                    "report_count": len(prepared_reports),
                },
            )
        return error_type
    return None


@router.post("/csp-report", status_code=202)
async def create_csp_report(
    request: Request,
    db: Session = Depends(get_db),  # noqa: B008
):
    """Receive bounded, allowlisted CSP violation reports without echoing data."""
    csp_reports_total.labels(outcome="received").inc()

    client_ip = _get_client_ip(request)
    rate_limit_allowed = await run_in_threadpool(
        check_rate_limit,
        client_ip,
        _CSP_REPORT_RATE_LIMIT_ACTION,
        window_seconds=_CSP_REPORT_RATE_LIMIT_WINDOW_SECONDS,
        max_requests=_CSP_REPORT_RATE_LIMIT_MAX_REQUESTS,
    )
    if not rate_limit_allowed:
        csp_reports_total.labels(outcome="rate_limited").inc()
        raise HTTPException(
            status_code=429,
            detail="CSP report rate limit exceeded",
            headers={"Retry-After": str(_CSP_REPORT_RATE_LIMIT_WINDOW_SECONDS)},
        )

    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
    if content_type not in _CSP_REPORT_CONTENT_TYPES:
        _reject_csp_report(415, "Unsupported CSP report Content-Type")

    body = await _read_bounded_csp_body(request)
    try:
        payload = json.loads(body, parse_constant=_reject_non_finite_json_constant)
    except ValueError:
        _reject_csp_report(400, "Invalid CSP report JSON")

    reports = _parse_csp_reports(content_type, payload)
    normalized_reports = [_normalize_csp_report(report) for report in reports]

    accepted = 0
    sampled = 0
    persist_failed = 0
    prepared_reports: list[tuple[str, dict[str, object]]] = []
    for normalized in normalized_reports:
        if not _should_sample_csp_report(normalized):
            sampled += 1
            csp_reports_total.labels(outcome="sampled").inc()
            continue
        prepared_reports.append((uuid.uuid4().hex, normalized))

    if prepared_reports:
        error_type = await run_in_threadpool(
            _persist_csp_reports,
            db,
            prepared_reports,
            trusted_environment=CSP_REPORT_ENVIRONMENT,
            trusted_release=RELEASE_COMMIT,
        )
        if error_type is not None:
            persist_failed = len(prepared_reports)
            csp_reports_total.labels(outcome="persist_failed").inc(persist_failed)
            for trace_id, _ in prepared_reports:
                logger.warning(
                    "csp_report_persist_failed",
                    extra={
                        "trace_id": trace_id,
                        "error_type": error_type,
                        "report_count": persist_failed,
                    },
                )
        else:
            accepted = len(prepared_reports)
            csp_reports_total.labels(outcome="accepted").inc(accepted)

    return {
        "accepted": accepted,
        "sampled": sampled,
        "persist_failed": persist_failed,
    }


@router.post("/frontend", status_code=202)
def create_frontend_log(
    request: Request,
    data: FrontendLogCreate,
    db: Session = Depends(get_db),  # noqa: B008
    current_user: UserDB | None = Depends(get_optional_current_user),  # noqa: B008
):
    """接收前端错误、日志和 Web Vitals 数据。

    鉴权策略：
    - 该端点允许匿名访问（未登录用户也能上报）
    - 如果请求携带有效 Authorization: Bearer token，user_id 从 token 解析
    - 客户端传入的 user_id 字段被忽略，防止伪造

    该端点不返回业务数据，仅确认接收（202 Accepted）。
    写入失败时降级为结构化日志，不向前端抛错。
    """
    # payload 大小硬限制
    if _payload_size_bytes(data) > _MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=422, detail="payload 大小超过 8KB 限制")

    # 身份归属：优先从 token 解析，忽略客户端 user_id
    effective_user_id = current_user.id if current_user else None

    meta = data.meta or {}
    try:
        db.add(
            FrontendLogDB(
                user_id=effective_user_id,
                log_type=data.type,
                level=data.level,
                url=meta.get("url"),
                user_agent=meta.get("ua"),
                release=meta.get("release"),
                environment=meta.get("environment"),
                payload_json=json.dumps(data.payload, ensure_ascii=False, default=str),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        # 降级：写入失败时记录到服务端日志，避免丢失关键前端错误
        # 不记录完整 payload，防止日志污染
        logger.warning(
            "frontend_log_persist_failed",
            extra={
                "log_type": data.type,
                "level": data.level,
                "url": meta.get("url"),
                "payload_size": _payload_size_bytes(data),
            },
        )
    return {"ok": True}


@router.get("/frontend", response_model=list[FrontendLogResponse])
def list_frontend_logs(
    response: Response,
    type: str | None = Query(None, max_length=20, description="日志类型筛选"),
    level: str | None = Query(None, max_length=20, description="日志级别筛选"),
    start_time: str | None = Query(None, description="起始时间（ISO 8601）"),
    end_time: str | None = Query(None, description="结束时间（ISO 8601）"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: UserDB = Depends(get_current_user_dependency),  # noqa: B008
    db: Session = Depends(get_db),  # noqa: B008
):
    """查询前端日志。

    权限策略：
    - admin 用户可查询全部日志
    - 普通用户只能查询与自己 user_id 关联的日志
    """
    q = db.query(FrontendLogDB)

    # 权限过滤
    if current_user.role != "admin":
        q = q.filter(FrontendLogDB.user_id == current_user.id)

    if type:
        q = q.filter(FrontendLogDB.log_type == type)
    if level:
        q = q.filter(FrontendLogDB.level == level)
    if start_time:
        try:
            # URL 查询参数中的 + 可能被解码为空格，先还原
            start_time = start_time.replace(" ", "+")
            parsed = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
            q = q.filter(FrontendLogDB.created_at >= parsed)
        except ValueError:
            pass
    if end_time:
        try:
            # URL 查询参数中的 + 可能被解码为空格，先还原
            end_time = end_time.replace(" ", "+")
            parsed = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
            q = q.filter(FrontendLogDB.created_at <= parsed)
        except ValueError:
            pass

    total = q.with_entities(func.count(FrontendLogDB.id)).scalar() or 0

    results = q.order_by(desc(FrontendLogDB.created_at)).offset(skip).limit(limit).all()

    response.headers["X-Total-Count"] = str(total)
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "type": r.log_type,
            "level": r.level,
            "url": r.url,
            "user_agent": r.user_agent,
            "release": r.release,
            "environment": r.environment,
            "payload": json.loads(r.payload_json) if r.payload_json else {},
            "created_at": r.created_at,
        }
        for r in results
    ]
