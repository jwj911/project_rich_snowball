"""期货连续合约数据回补脚本 — 自动发现、直接查询、逐条插入。"""

import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import psycopg2
import tushare as ts
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")

TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN")
if not TUSHARE_TOKEN:
    print("ERROR: TUSHARE_TOKEN not set")
    sys.exit(1)

ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

HOLIDAYS = {
    date(2024, 1, 1),
    date(2024, 2, 9),
    date(2024, 2, 12),
    date(2024, 2, 13),
    date(2024, 2, 14),
    date(2024, 2, 15),
    date(2024, 2, 16),
    date(2024, 4, 4),
    date(2024, 4, 5),
    date(2024, 5, 1),
    date(2024, 5, 2),
    date(2024, 5, 3),
    date(2024, 6, 10),
    date(2024, 9, 16),
    date(2024, 9, 17),
    date(2024, 10, 1),
    date(2024, 10, 2),
    date(2024, 10, 3),
    date(2024, 10, 4),
    date(2024, 10, 7),
    date(2025, 1, 1),
    date(2025, 1, 28),
    date(2025, 1, 29),
    date(2025, 1, 30),
    date(2025, 1, 31),
    date(2025, 2, 3),
    date(2025, 2, 4),
    date(2025, 4, 4),
    date(2025, 5, 1),
    date(2025, 5, 2),
    date(2025, 5, 5),
    date(2025, 6, 2),
    date(2025, 10, 1),
    date(2025, 10, 2),
    date(2025, 10, 3),
    date(2025, 10, 6),
    date(2025, 10, 7),
    date(2025, 10, 8),
    date(2026, 1, 1),
    date(2026, 1, 2),
    date(2026, 2, 16),
    date(2026, 2, 17),
    date(2026, 2, 18),
    date(2026, 2, 19),
    date(2026, 2, 20),
    date(2026, 2, 23),
    date(2026, 2, 24),
    date(2026, 4, 6),
    date(2026, 5, 1),
    date(2026, 5, 4),
    date(2026, 5, 5),
    date(2026, 6, 19),
    date(2026, 6, 22),
}


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS


def get_conn():
    return psycopg2.connect(
        host="localhost", port=15432, database="futures_community", user="futures", password="futures123"
    )


def get_continuous_contracts(cursor):
    cursor.execute("""
        SELECT DISTINCT ts_code, MAX(variety_id)
        FROM fut_daily_data
        WHERE period = 'D'
        GROUP BY ts_code
        HAVING ts_code ~ '^[A-Za-z]+\\.[A-Za-z]+$'
        ORDER BY ts_code
    """)
    return cursor.fetchall()


def get_missing_dates(cursor, ts_code, start, end):
    cursor.execute(
        "SELECT DATE(trade_date)::date FROM fut_daily_data WHERE ts_code=%s AND period='D' AND trade_date>=%s AND trade_date<=%s",
        (ts_code, start, end),
    )
    existing = {r[0] for r in cursor.fetchall()}
    expected = [d for d in [start + timedelta(days=i) for i in range((end - start).days + 1)] if is_trading_day(d)]
    return [d for d in expected if d not in existing]


def fetch_and_insert(cursor, ts_code, variety_id, missing):
    if not missing:
        return 0, 0
    start_str = missing[0].strftime("%Y%m%d")
    end_str = missing[-1].strftime("%Y%m%d")

    try:
        df = pro.fut_daily(ts_code=ts_code, start_date=start_str, end_date=end_str)
        if df is None or df.empty:
            print(f"  {ts_code}: Tushare returned empty")
            return 0, len(missing)
        rows = df.to_dict("records")
    except Exception as e:
        print(f"  {ts_code}: Tushare error: {e}")
        return 0, len(missing)

    inserted = 0
    for raw in rows:
        td = str(raw.get("trade_date", ""))
        if len(td) != 8:
            continue
        trade_date = f"{td[:4]}-{td[4:6]}-{td[6:]}"
        cursor.execute(
            """
            INSERT INTO fut_daily_data (variety_id, ts_code, trade_date, period,
                pre_close, pre_settle, open_price, high_price, low_price, close_price,
                settle, change1, change2, volume, amount, open_interest, oi_chg)
            VALUES (%s, %s, %s, 'D',
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (variety_id, ts_code, period, trade_date) DO NOTHING
        """,
            (
                variety_id,
                raw.get("ts_code"),
                trade_date,
                raw.get("pre_close"),
                raw.get("pre_settle"),
                raw.get("open"),
                raw.get("high"),
                raw.get("low"),
                raw.get("close"),
                raw.get("settle"),
                raw.get("change1"),
                raw.get("change2"),
                raw.get("vol"),
                raw.get("amount"),
                raw.get("oi"),
                raw.get("oi_chg"),
            ),
        )
        if cursor.rowcount > 0:
            inserted += 1

    return inserted, len(missing) - inserted


def main():
    conn = get_conn()
    cursor = conn.cursor()

    contracts = get_continuous_contracts(cursor)
    print(f"发现 {len(contracts)} 个连续合约\n")

    start = date(2026, 6, 1)
    end = date(2026, 7, 5)
    total_inserted = 0
    total_missing = 0

    for ts_code, variety_id in contracts:
        missing = get_missing_dates(cursor, ts_code, start, end)
        if not missing:
            continue
        print(f"[BACKFILL] {ts_code}: {len(missing)} missing day(s) {missing[0]}~{missing[-1]}")
        inserted, still_missing = fetch_and_insert(cursor, ts_code, variety_id, missing)
        conn.commit()
        print(f"  inserted={inserted}, still_missing={still_missing}")
        total_inserted += inserted
        total_missing += still_missing
        time.sleep(0.6)

    cursor.close()
    conn.close()
    print(f"\n总计: 插入 {total_inserted} 条, 仍缺失 {total_missing} 天")


if __name__ == "__main__":
    main()
