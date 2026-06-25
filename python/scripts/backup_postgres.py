#!/usr/bin/env python3
"""PostgreSQL 自动备份脚本。

支持逻辑备份（pg_dump）与物理备份（pg_basebackup），并按保留策略清理过期备份。

典型用法::

    python scripts/backup_postgres.py --type logical
    python scripts/backup_postgres.py --type physical
    python scripts/backup_postgres.py --type logical --dry-run
    python scripts/backup_postgres.py --type all --backup-dir /var/backups/futures

配置来源（优先级从高到低）：命令行参数 > PG* 环境变量 > DATABASE_URL > 默认值。
"""

import argparse
import re
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from scripts._pg_utils import build_pg_command, merge_connection_params, pg_env, run_command

DEFAULT_BACKUP_DIR = Path("backups")
DEFAULT_LOGICAL_RETENTION_DAYS = 30
DEFAULT_PHYSICAL_RETENTION_DAYS = 7


def logical_backup(params: dict[str, str], backup_dir: Path, *, dry_run: bool = False) -> Path:
    """执行 ``pg_dump -Fc`` 逻辑备份，返回备份文件路径。"""
    dbname = params.get("dbname", "futures_community")
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    dump_dir = backup_dir / "pg_dump"
    dump_dir.mkdir(parents=True, exist_ok=True)
    dump_file = dump_dir / f"{dbname}_{timestamp}.dump"

    cmd = build_pg_command("pg_dump", params)
    cmd.extend(["-d", dbname, "-Fc", "-f", str(dump_file)])

    print(f"Starting logical backup: {dump_file}")
    run_command(cmd, pg_env(params), dry_run=dry_run)
    print(f"Logical backup completed: {dump_file}")
    return dump_file


def physical_backup(params: dict[str, str], backup_dir: Path, *, dry_run: bool = False) -> Path:
    """执行 ``pg_basebackup`` 物理备份，返回备份目录路径。"""
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    base_dir = backup_dir / "pg_base" / timestamp
    base_dir.mkdir(parents=True, exist_ok=True)

    cmd = build_pg_command("pg_basebackup", params)
    cmd.extend(["-D", str(base_dir), "-Ft", "-z", "-P", "-X", "stream"])

    print(f"Starting physical backup: {base_dir}")
    run_command(cmd, pg_env(params), dry_run=dry_run)
    print(f"Physical backup completed: {base_dir}")
    return base_dir


def cleanup_old_backups(
    backup_dir: Path,
    retention_days: int,
    pattern: str,
    *,
    dry_run: bool = False,
) -> int:
    """删除匹配正则且超过保留期限的备份文件或目录。"""
    if not backup_dir.exists():
        return 0

    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    removed = 0

    for item in backup_dir.iterdir():
        if not re.match(pattern, item.name):
            continue
        try:
            mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=UTC)
        except OSError:
            continue

        if mtime < cutoff:
            if dry_run:
                print(f"[DRY-RUN] Would remove {item}")
            else:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                print(f"Removed old backup: {item}")
            removed += 1

    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="PostgreSQL backup automation")
    parser.add_argument(
        "--type",
        choices=["logical", "physical", "all"],
        required=True,
        help="Backup type: logical (pg_dump), physical (pg_basebackup), or all",
    )
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=DEFAULT_BACKUP_DIR,
        help=f"Backup root directory (default: {DEFAULT_BACKUP_DIR})",
    )
    parser.add_argument("--host", help="PostgreSQL host")
    parser.add_argument("--port", help="PostgreSQL port")
    parser.add_argument("--user", help="PostgreSQL user")
    parser.add_argument("--password", help="PostgreSQL password")
    parser.add_argument("--dbname", help="PostgreSQL database name")
    parser.add_argument(
        "--logical-retention-days",
        type=int,
        default=DEFAULT_LOGICAL_RETENTION_DAYS,
        help=f"Logical backup retention days (default: {DEFAULT_LOGICAL_RETENTION_DAYS})",
    )
    parser.add_argument(
        "--physical-retention-days",
        type=int,
        default=DEFAULT_PHYSICAL_RETENTION_DAYS,
        help=f"Physical backup retention days (default: {DEFAULT_PHYSICAL_RETENTION_DAYS})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")

    args = parser.parse_args()
    params = merge_connection_params(args)

    if not params.get("dbname"):
        print(
            "ERROR: database name is required (set --dbname or PGDATABASE or DATABASE_URL)",
            file=sys.stderr,
        )
        return 1

    print(f"Backup target: {params.get('host', 'localhost')}:{params.get('port', '5432')}/{params['dbname']}")

    try:
        if args.type in ("logical", "all"):
            logical_backup(params, args.backup_dir, dry_run=args.dry_run)
            cleanup_old_backups(
                args.backup_dir / "pg_dump",
                args.logical_retention_days,
                r".*_\d{8}_\d{6}\.dump",
                dry_run=args.dry_run,
            )

        if args.type in ("physical", "all"):
            physical_backup(params, args.backup_dir, dry_run=args.dry_run)
            cleanup_old_backups(
                args.backup_dir / "pg_base",
                args.physical_retention_days,
                r"\d{8}_\d{6}",
                dry_run=args.dry_run,
            )
    except subprocess.CalledProcessError as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        if exc.stderr:
            print(exc.stderr, file=sys.stderr, end="")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1

    print("Backup operation completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
