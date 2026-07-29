#!/usr/bin/env python3
"""只读生产发布预检命令。

除写入指定的 JSON 报告外，本命令不连接或修改数据库、Redis、部署状态和发布清单。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.release_preflight import ReleasePreflightInput, run_release_preflight  # noqa: E402

EXIT_PASSED = 0
EXIT_GATE_FAILED = 1
EXIT_REPORT_WRITE_FAILED = 2
DEFAULT_REPORT_PATH = Path("release_preflight_report.json")

_ARGUMENT_TO_ENV = {
    "environment": "ENV",
    "database_url": "DATABASE_URL",
    "secret_key": "SECRET_KEY",
    "cors_origins": "CORS_ORIGINS",
    "data_source": "DATA_SOURCE",
    "redis_url": "REDIS_URL",
    "release_commit": "RELEASE_COMMIT",
    "release_window_utc": "RELEASE_WINDOW_UTC",
    "release_owner": "RELEASE_OWNER",
    "rollback_owner": "ROLLBACK_OWNER",
    "sse_deployment_mode": "SSE_DEPLOYMENT_MODE",
}


def build_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="Run read-only production release gates")
    parser.add_argument("--env", dest="environment", help="Deployment environment; must be production")
    parser.add_argument("--database-url", help="PostgreSQL DATABASE_URL")
    parser.add_argument("--secret-key", help="Application SECRET_KEY")
    parser.add_argument("--cors-origins", help="Comma-separated HTTPS CORS origins")
    parser.add_argument("--data-source", help="Production market data source")
    parser.add_argument("--redis-url", help="Redis connection URL")
    parser.add_argument("--release-commit", help="Commit selected for release")
    parser.add_argument("--release-window-utc", help="UTC timestamp or start/end interval")
    parser.add_argument("--release-owner", help="Release owner")
    parser.add_argument("--rollback-owner", help="Rollback owner")
    parser.add_argument("--sse-deployment-mode", help="Supported values: single or sticky")
    parser.add_argument(
        "--report-path",
        "--report",
        dest="report_path",
        type=Path,
        help="JSON report output path; defaults to RELEASE_PREFLIGHT_REPORT_PATH or release_preflight_report.json",
    )
    return parser


def main(argv: Sequence[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    """执行预检、写报告并返回稳定退出码。"""
    args = build_parser().parse_args(argv)
    source_environment = os.environ if environ is None else environ
    values = dict(source_environment)
    for argument_name, environment_name in _ARGUMENT_TO_ENV.items():
        argument_value = getattr(args, argument_name)
        if argument_value is not None:
            values[environment_name] = argument_value
            if environment_name == "CORS_ORIGINS":
                values["ALLOW_ORIGINS"] = ""

    report = run_release_preflight(ReleasePreflightInput.from_mapping(values))
    report_payload = report.to_json()
    report_path = args.report_path or Path(source_environment.get("RELEASE_PREFLIGHT_REPORT_PATH", DEFAULT_REPORT_PATH))

    try:
        report_path.write_text(f"{report_payload}\n", encoding="utf-8")
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
    return EXIT_PASSED if report.passed else EXIT_GATE_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
