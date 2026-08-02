#!/usr/bin/env python3
"""Plan or apply idempotent PostgreSQL K-line shadow partitions."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
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
    apply_kline_partition_plan,
    build_kline_partition_plan,
)

EXIT_SUCCESS = 0
EXIT_REFUSED = 2
EXIT_DATABASE_ERROR = 3


def build_parser() -> argparse.ArgumentParser:
    """Create the partition management parser."""
    parser = argparse.ArgumentParser(description="Plan K-line shadow partition DDL; dry-run is the default")
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
        help="Execute the plan; omitted means print-only dry-run",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirm execution against the explicit shadow table",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    """Print a plan by default, or apply it after all safety gates pass."""
    args = build_parser().parse_args(argv)
    try:
        plan = build_kline_partition_plan(args.shadow_table)
    except KlinePartitioningError as exc:
        _emit_error("unsafe_shadow_table", type(exc).__name__)
        return EXIT_REFUSED

    if not args.apply:
        print(plan.to_sql())
        return EXIT_SUCCESS

    if not args.confirm:
        _emit_error("confirmation_required", "MissingConfirmFlag")
        return EXIT_REFUSED

    source_environment = os.environ if environ is None else environ
    database_url = args.database_url or source_environment.get("DATABASE_URL")
    if not database_url:
        _emit_error("database_url_required", "MissingDatabaseUrl")
        return EXIT_REFUSED

    try:
        backend_name = make_url(database_url).get_backend_name().casefold()
    except Exception as exc:
        _emit_error("invalid_database_url", type(exc).__name__)
        return EXIT_REFUSED
    if backend_name != "postgresql":
        _emit_error(
            "postgresql_required",
            UnsupportedPartitionDialectError.__name__,
        )
        return EXIT_REFUSED

    engine = None
    try:
        engine = create_engine(database_url, pool_pre_ping=True)
        if engine.dialect.name.casefold() != "postgresql":
            raise UnsupportedPartitionDialectError
        with engine.begin() as connection:
            statement_count = apply_kline_partition_plan(connection, plan)
    except UnsupportedPartitionDialectError as exc:
        _emit_error("postgresql_required", type(exc).__name__)
        return EXIT_REFUSED
    except Exception as exc:
        _emit_error("partition_apply_failed", type(exc).__name__)
        return EXIT_DATABASE_ERROR
    finally:
        if engine is not None:
            with contextlib.suppress(Exception):
                engine.dispose()

    print(
        json.dumps(
            {
                "shadow_table": plan.shadow_table,
                "statement_count": statement_count,
                "status": "applied",
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return EXIT_SUCCESS


def _emit_error(code: str, error_type: str) -> None:
    print(
        json.dumps(
            {
                "error": {
                    "code": code,
                    "error_type": error_type,
                },
                "status": "refused",
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ),
        file=sys.stderr,
    )


if __name__ == "__main__":
    raise SystemExit(main())
