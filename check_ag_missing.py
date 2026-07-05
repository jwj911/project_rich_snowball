import os, sys
from pathlib import Path
from datetime import date, timedelta

root = Path(__file__).parent
sys.path.insert(0, str(root / 'python'))

import psycopg2
conn = psycopg2.connect(host="localhost", port=15432, database="futures_community",
                        user="futures", password="futures123")
cursor = conn.cursor()

# 获取 AG.SHF 所有历史数据
cursor.execute("""
    SELECT DATE(trade_date)::date as d
    FROM fut_daily_data
    WHERE ts_code = 'AG.SHF' AND period = 'D'
    ORDER BY d
""")
actual_dates = [r[0] for r in cursor.fetchall()]

# 2024-07-05 至今的理论交易日（简单：周一到周五，刨除已知节假日）
HOLIDAYS = {
    date(2024,1,1), date(2024,2,9), date(2024,2,12), date(2024,2,13), date(2024,2,14),
    date(2024,2,15), date(2024,2,16), date(2024,4,4), date(2024,4,5),
    date(2024,5,1), date(2024,5,2), date(2024,5,3), date(2024,6,10),
    date(2024,9,16), date(2024,9,17), date(2024,10,1), date(2024,10,2),
    date(2024,10,3), date(2024,10,4), date(2024,10,7),
    date(2025,1,1), date(2025,1,28), date(2025,1,29), date(2025,1,30), date(2025,1,31),
    date(2025,2,3), date(2025,2,4), date(2025,4,4), date(2025,5,1), date(2025,5,2),
    date(2025,5,5), date(2025,6,2), date(2025,10,1), date(2025,10,2), date(2025,10,3),
    date(2025,10,6), date(2025,10,7), date(2025,10,8),
    date(2026,1,1), date(2026,1,2), date(2026,2,16), date(2026,2,17), date(2026,2,18),
    date(2026,2,19), date(2026,2,20), date(2026,2,23), date(2026,2,24), date(2026,4,6),
    date(2026,5,1), date(2026,5,4), date(2026,5,5), date(2026,6,19), date(2026,6,22),
}

def is_trading_day(d):
    return d.weekday() < 5 and d not in HOLIDAYS

start = actual_dates[0] if actual_dates else date(2024,7,5)
end = actual_dates[-1] if actual_dates else date(2026,7,5)
today = date(2026, 7, 5)

expected = set()
d = start
while d <= today:
    if is_trading_day(d):
        expected.add(d)
    d += timedelta(days=1)

actual = set(actual_dates)
missing = sorted(expected - actual)

print(f"AG.SHF 数据范围: {actual_dates[0]} ~ {actual_dates[-1]}")
print(f"理论交易日: {len(expected)} 天")
print(f"实际有数据: {len(actual)} 天")
print(f"缺失: {len(missing)} 天\n")

if missing:
    print("缺失日期:")
    for d in missing:
        print(f"  {d} ({['周一','周二','周三','周四','周五'][d.weekday()]})")

conn.close()
