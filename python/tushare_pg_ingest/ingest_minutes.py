"""Optional ft_mins ingestion placeholder.

Purpose:
    Historical minute data is intentionally not part of the default backfill
    because Tushare marks ``ft_mins`` as a separately permissioned and
    frequency-limited interface.  This module exists so that the workflow has
    a clear extension point once minute-level permissions are granted.

Tushare API (not currently called):
    ``ft_mins`` - historical minute bars for futures contracts.

Target database table (planned):
    ``fut_minute_data`` or similar (schema not yet defined).

Key CLI arguments:
    None - the script exits immediately with a message.

Usage example:
    python ingest_minutes.py

Known limitations:
    - This script does not perform any I/O; it merely prints an advisory
      message and returns exit code 2.
    - Before enabling, confirm Tushare Pro subscription includes the
      ``ft_mins`` interface and that rate limits are documented.
"""

from __future__ import annotations


def main() -> int:
    """Print advisory message and return a non-zero exit code."""
    print(
        "ft_mins is intentionally disabled in this phase. "
        "Use daily/weekly/monthly backfills first; enable this after minute-data permission is confirmed."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
