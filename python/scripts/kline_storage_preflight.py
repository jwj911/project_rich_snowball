#!/usr/bin/env python3
"""Run the read-only K-line storage capacity preflight."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.kline_storage import (  # noqa: E402
    KlineStorageStatus,
    build_kline_storage_failure_report,
    database_url_sensitive_values,
    run_kline_storage_preflight,
)

EXIT_SUCCESS = 0
EXIT_GATE_FAILED = 1
EXIT_REPORT_WRITE_FAILED = 2
DEFAULT_DATABASE_URL = "sqlite:///./futures_community.db"

_SENSITIVE_KEY_MARKERS = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "API_KEY",
    "DATABASE_URL",
    "REDIS_URL",
)


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(description="Run read-only K-line storage capacity gates")
    parser.add_argument(
        "--database-url",
        help="Database URL; defaults to DATABASE_URL or the local SQLite database",
    )
    parser.add_argument(
        "--minute-query-p99-ms",
        type=_non_negative_float,
        help="P99 from an external read-only minute-query benchmark",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        required=True,
        help="Explicit JSON report output path",
    )
    return parser


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    """Collect evidence, write the report, and return a stable exit code."""
    args = build_parser().parse_args(argv)
    source_environment = os.environ if environ is None else environ
    database_url = args.database_url or source_environment.get("DATABASE_URL") or DEFAULT_DATABASE_URL
    sensitive_values = _collect_sensitive_values(source_environment, database_url)
    trace_id = uuid.uuid4().hex
    engine = None

    try:
        engine = create_engine(database_url)
        report = run_kline_storage_preflight(
            engine,
            minute_query_p99_ms=args.minute_query_p99_ms,
            trace_id=trace_id,
            sensitive_values=sensitive_values,
        )
    except Exception as exc:
        report = build_kline_storage_failure_report(
            type(exc).__name__,
            trace_id=trace_id,
            sensitive_values=sensitive_values,
        )
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception as exc:
                report = build_kline_storage_failure_report(
                    type(exc).__name__,
                    trace_id=trace_id,
                    sensitive_values=sensitive_values,
                )

    report_payload = report.to_json()
    try:
        args.report_path.write_text(f"{report_payload}\n", encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        print(
            json.dumps(
                {
                    "trace_id": report.trace_id,
                    "status": "report_write_failed",
                    "error_type": type(exc).__name__,
                },
                ensure_ascii=True,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return EXIT_REPORT_WRITE_FAILED

    print(report_payload)
    return EXIT_SUCCESS if report.status is KlineStorageStatus.NOT_REQUIRED else EXIT_GATE_FAILED


def _non_negative_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a non-negative number") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise argparse.ArgumentTypeError("must be a finite non-negative number")
    return parsed


def _collect_sensitive_values(
    environment: Mapping[str, str],
    database_url: str,
) -> tuple[str, ...]:
    values = list(database_url_sensitive_values(database_url))
    for key, value in environment.items():
        normalized_key = str(key).upper()
        if value and any(marker in normalized_key for marker in _SENSITIVE_KEY_MARKERS):
            values.append(str(value))
    return tuple(dict.fromkeys(values))


if __name__ == "__main__":
    raise SystemExit(main())
