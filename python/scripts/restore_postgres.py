#!/usr/bin/env python3
"""PostgreSQL 逻辑备份恢复演练脚本。

将 ``pg_dump -Fc`` 自定义格式备份恢复到目标数据库，并校验核心表行数。

典型用法::

    python scripts/restore_postgres.py --backup-file backups/pg_dump/futures_community_20260527_120000.dump
    python scripts/restore_postgres.py --backup-file xxx.dump --target-db futures_community_restore --drop-target
"""

import argparse
import subprocess
import sys
from pathlib import Path

from scripts._pg_utils import build_pg_command, merge_connection_params, pg_env, run_command

# 恢复后校验的核心表。顺序按业务重要性排列，便于快速发现缺失。
CORE_TABLES = [
    "users",
    "varieties",
    "comments",
    "price_levels",
    "watchlists",
    "opinions",
    "trade_records",
    "news_sources",
    "news_articles",
]


def target_exists(params: dict[str, str], target_db: str) -> bool:
    """检查目标数据库是否存在。"""
    cmd = build_pg_command("psql", params)
    cmd.extend(
        [
            "-d",
            "postgres",
            "-tAc",
            f"SELECT 1 FROM pg_database WHERE datname='{target_db}'",
        ]
    )
    result = subprocess.run(cmd, env=pg_env(params), capture_output=True, text=True)
    return result.returncode == 0 and result.stdout.strip() == "1"


def drop_database(params: dict[str, str], target_db: str, *, dry_run: bool = False) -> None:
    """删除目标数据库（如果存在）。"""
    if not target_exists(params, target_db):
        return
    cmd = build_pg_command("dropdb", params) + [target_db]
    print(f"Dropping target database: {target_db}")
    run_command(cmd, pg_env(params), dry_run=dry_run)


def create_database(params: dict[str, str], target_db: str, *, dry_run: bool = False) -> None:
    """创建目标数据库。"""
    cmd = build_pg_command("createdb", params) + [target_db]
    print(f"Creating target database: {target_db}")
    run_command(cmd, pg_env(params), dry_run=dry_run)


def restore_backup(
    params: dict[str, str],
    target_db: str,
    backup_file: Path,
    *,
    dry_run: bool = False,
) -> None:
    """使用 ``pg_restore`` 将备份恢复到目标数据库。"""
    cmd = build_pg_command("pg_restore", params)
    cmd.extend(["-d", target_db, str(backup_file)])
    print(f"Restoring backup to {target_db}: {backup_file}")
    run_command(cmd, pg_env(params), dry_run=dry_run)


def verify_row_counts(
    params: dict[str, str],
    target_db: str,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """查询目标数据库核心表行数并返回。"""
    counts: dict[str, int] = {}
    for table in CORE_TABLES:
        cmd = build_pg_command("psql", params)
        cmd.extend(["-d", target_db, "-tAc", f"SELECT count(*) FROM {table}"])
        if dry_run:
            print(f"[DRY-RUN] {' '.join(cmd)}")
            counts[table] = 0
            continue

        result = subprocess.run(cmd, env=pg_env(params), capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Warning: failed to count rows for {table}: {result.stderr.strip()}")
            counts[table] = -1
            continue
        try:
            counts[table] = int(result.stdout.strip())
        except ValueError:
            counts[table] = -1
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="PostgreSQL restore drill script")
    parser.add_argument(
        "--backup-file",
        type=Path,
        required=True,
        help="Path to pg_dump custom-format backup",
    )
    parser.add_argument(
        "--target-db",
        default="futures_community_restore",
        help="Target database name (default: futures_community_restore)",
    )
    parser.add_argument(
        "--drop-target",
        action="store_true",
        help="Drop target database before restore if it exists",
    )
    parser.add_argument("--host", help="PostgreSQL host")
    parser.add_argument("--port", help="PostgreSQL port")
    parser.add_argument("--user", help="PostgreSQL user")
    parser.add_argument("--password", help="PostgreSQL password")
    parser.add_argument(
        "--dbname",
        help="PostgreSQL database name (used as maintenance db for createdb/dropdb)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")

    args = parser.parse_args()
    params = merge_connection_params(args)

    if not args.backup_file.exists():
        print(f"ERROR: backup file not found: {args.backup_file}", file=sys.stderr)
        return 1

    print(f"Restore target host: {params.get('host', 'localhost')}:{params.get('port', '5432')}")
    print(f"Restore source: {args.backup_file}")
    print(f"Restore target database: {args.target_db}")

    try:
        if args.drop_target:
            drop_database(params, args.target_db, dry_run=args.dry_run)

        create_database(params, args.target_db, dry_run=args.dry_run)
        restore_backup(params, args.target_db, args.backup_file, dry_run=args.dry_run)

        print("Verifying core table row counts...")
        counts = verify_row_counts(params, args.target_db, dry_run=args.dry_run)
        for table, count in counts.items():
            print(f"  {table}: {count}")
    except subprocess.CalledProcessError as exc:
        print(f"Restore failed: {exc}", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr, end="")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Restore failed: {exc}", file=sys.stderr)
        return 1

    print("Restore drill completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
