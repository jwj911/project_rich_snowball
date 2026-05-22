"""
结构化日志配置
===============
基于 structlog 的统一日志输出：
- 开发环境：彩色、可读的键值对格式
- 生产环境：JSON 格式，便于日志平台解析
- 自动对敏感字段（密码、token、数据库连接串）脱敏
- 与标准库 logging 桥接，确保第三方库日志也能被捕获
"""

import logging
import re
import sys

import structlog

from config import ENV

# 敏感字段正则：用于脱敏
_SENSITIVE_PATTERNS = [
    (re.compile(r"(password|passwd|pwd|secret|token|api_key)\s*[=:]\s*[^\s,;]+", re.IGNORECASE), r"\1=***"),
    (re.compile(r"(postgresql://[^:]+:)([^@]+)(@.+)", re.IGNORECASE), r"\1***\3"),
    (re.compile(r"(redis://:)([^@]+)(@.+)", re.IGNORECASE), r"\1***\3"),
]


def _redact_message(message: str) -> str:
    """对日志消息中的敏感信息进行脱敏处理。"""
    if not isinstance(message, str):
        return message
    for pattern, replacement in _SENSITIVE_PATTERNS:
        message = pattern.sub(replacement, message)
    return message


def redact_processor(logger, method_name, event_dict):
    """structlog 处理器：对 event 和异常信息进行脱敏。"""
    if "event" in event_dict and isinstance(event_dict["event"], str):
        event_dict["event"] = _redact_message(event_dict["event"])
    if "exception" in event_dict and isinstance(event_dict.get("exception"), str):
        event_dict["exception"] = _redact_message(event_dict["exception"])
    return event_dict


def setup_logging():
    """配置结构化日志。应在应用入口（main.py / worker.py）最早调用。"""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        redact_processor,
    ]

    if ENV == "production":
        # 生产环境：JSON 输出
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        # 开发环境：彩色控制台输出
        processors = shared_processors + [
            structlog.dev.set_exc_info,
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # 将标准库 logging 桥接到 structlog
    # 这样第三方库（如 uvicorn、sqlalchemy）的日志也会被结构化
    handler = logging.StreamHandler(sys.stdout)
    if ENV == "production":
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer(),
            foreign_pre_chain=shared_processors,
        )
    else:
        formatter = structlog.stdlib.ProcessorFormatter(
            processor=structlog.dev.ConsoleRenderer(colors=True),
            foreign_pre_chain=shared_processors,
        )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)

    # 降低某些第三方库的日志级别
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
