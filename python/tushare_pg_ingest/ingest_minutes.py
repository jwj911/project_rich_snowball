"""Optional ft_mins ingestion placeholder.

Historical minute data is intentionally not part of the default backfill because
Tushare marks it as a separately permissioned/frequency-limited interface. Keep
this entry point so the workflow has a clear place to extend later.
"""

from __future__ import annotations


def main() -> int:
    print(
        "ft_mins is intentionally disabled in this phase. "
        "Use daily/weekly/monthly backfills first; enable this after minute-data permission is confirmed."
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

