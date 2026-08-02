#!/usr/bin/env python3
"""Safely rehearse copying active K-line data into a PostgreSQL shadow table."""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.kline_partitioning import (  # noqa: E402
    KlinePartitioningError,
    UnsupportedPartitionDialectError,
)
from services.kline_rehearsal import (  # noqa: E402
    InvalidRehearsalSourceError,
    KlineRehearsalCheckCode,
    build_kline_rehearsal_dry_run_report,
    build_kline_rehearsal_failure_report,
    run_kline_copy_rehearsal,
)

EXIT_SUCCESS = 0
EXIT_REFUSED = 2
EXIT_DATABASE_ERROR = 3


def build_parser() -> argparse.ArgumentParser:
    """Create the isolated copy rehearsal parser."""
    parser = argparse.ArgumentParser(
        description=("Rehearse an explicit kline_data-to-shadow copy; dry-run is the default")
    )
    parser.add_argument(
        "--source-table",
        required=True,
        help="Explicit source table; must be exactly kline_data",
    )
    parser.add_argument(
        "--shadow-table",
        required=True,
        help="Explicit safe shadow table name containing a standalone 'shadow' token",
    )
    parser.add_argument(
        "--database-url",
        help="PostgreSQL URL; required for --apply, or supplied by DATABASE_URL",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Run the isolated copy rehearsal; omitted means aggregate-free dry-run",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm writes to the explicit shadow table",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Drop the rehearsal shadow table and sequence after successful validation",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Print a dry-run report or execute after all safety gates pass."""
    args = build_parser().parse_args(argv)
    trace_id = uuid.uuid4().hex

    try:
        dry_run_report = build_kline_rehearsal_dry_run_report(
            args.source_table,
            args.shadow_table,
            cleanup_on_success=args.cleanup,
            trace_id=trace_id,
        )
    except (KlinePartitioningError, InvalidRehearsalSourceError) as exc:
        _emit_report(
            build_kline_rehearsal_failure_report(
                args.source_table,
                args.shadow_table,
                error_code=_safety_error_code(exc),
                error_type=type(exc).__name__,
                cleanup_on_success=args.cleanup,
                trace_id=trace_id,
            ),
            error=True,
        )
        return EXIT_REFUSED

    if not args.apply:
        _emit_report(dry_run_report)
        return EXIT_SUCCESS

    if not args.confirm:
        _emit_report(
            build_kline_rehearsal_failure_report(
                args.source_table,
                args.shadow_table,
                error_code="KLINE_REHEARSAL_CONFIRMATION_REQUIRED",
                error_type="MissingConfirmFlag",
                cleanup_on_success=args.cleanup,
                trace_id=trace_id,
            ),
            error=True,
        )
        return EXIT_REFUSED

    source_environment = os.environ if environ is None else environ
    database_url = args.database_url or source_environment.get("DATABASE_URL")
    if not database_url:
        _emit_report(
            build_kline_rehearsal_failure_report(
                args.source_table,
                args.shadow_table,
                error_code="KLINE_REHEARSAL_DATABASE_URL_REQUIRED",
                error_type="MissingDatabaseUrl",
                cleanup_on_success=args.cleanup,
                trace_id=trace_id,
            ),
            error=True,
        )
        return EXIT_REFUSED

    try:
        backend_name = make_url(database_url).get_backend_name().casefold()
    except Exception as exc:
        _emit_report(
            build_kline_rehearsal_failure_report(
                args.source_table,
                args.shadow_table,
                error_code="KLINE_REHEARSAL_INVALID_DATABASE_URL",
                error_type=type(exc).__name__,
                cleanup_on_success=args.cleanup,
                trace_id=trace_id,
            ),
            error=True,
        )
        return EXIT_REFUSED
    if backend_name != "postgresql":
        _emit_report(
            build_kline_rehearsal_failure_report(
                args.source_table,
                args.shadow_table,
                error_code="KLINE_REHEARSAL_POSTGRESQL_REQUIRED",
                error_type=UnsupportedPartitionDialectError.__name__,
                cleanup_on_success=args.cleanup,
                trace_id=trace_id,
            ),
            error=True,
        )
        return EXIT_REFUSED

    engine = None
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        if engine.dialect.name.casefold() != "postgresql":
            raise UnsupportedPartitionDialectError
        report = run_kline_copy_rehearsal(
            engine,
            args.source_table,
            args.shadow_table,
            cleanup_on_success=args.cleanup,
            trace_id=trace_id,
        )
    except UnsupportedPartitionDialectError as exc:
        report = build_kline_rehearsal_failure_report(
            args.source_table,
            args.shadow_table,
            error_code="KLINE_REHEARSAL_POSTGRESQL_REQUIRED",
            error_type=type(exc).__name__,
            cleanup_on_success=args.cleanup,
            trace_id=trace_id,
        )
    except Exception as exc:
        report = build_kline_rehearsal_failure_report(
            args.source_table,
            args.shadow_table,
            error_code=KlineRehearsalCheckCode.EXECUTION.value,
            error_type=type(exc).__name__,
            cleanup_on_success=args.cleanup,
            trace_id=trace_id,
        )
    finally:
        if engine is not None:
            with contextlib.suppress(Exception):
                engine.dispose()

    _emit_report(report, error=not report.passed)
    return EXIT_SUCCESS if report.passed else EXIT_DATABASE_ERROR


def _safety_error_code(exc: Exception) -> str:
    if isinstance(exc, InvalidRehearsalSourceError):
        return KlineRehearsalCheckCode.SOURCE_TABLE.value
    return KlineRehearsalCheckCode.SHADOW_NAMESPACE.value


def _emit_report(report, *, error: bool = False) -> None:
    print(report.to_json(), file=sys.stderr if error else sys.stdout)


if __name__ == "__main__":
    raise SystemExit(main())
