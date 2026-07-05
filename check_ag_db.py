import psycopg2
conn = psycopg2.connect(host='localhost', port=15432, database='futures_community',
                        user='futures', password='futures123')
cursor = conn.cursor()

print("=== AG.SHF 2026-05 数据库日期 ===")
cursor.execute("""
    SELECT DATE(trade_date)::date
    FROM fut_daily_data
    WHERE ts_code = 'AG.SHF' AND period = 'D'
      AND trade_date >= '2026-05-01' AND trade_date <= '2026-05-31'
    ORDER BY trade_date
""")
for r in cursor.fetchall():
    print(f"  {r[0]}")

print("\n=== AG.SHF 2026-06 数据库日期 ===")
cursor.execute("""
    SELECT DATE(trade_date)::date
    FROM fut_daily_data
    WHERE ts_code = 'AG.SHF' AND period = 'D'
      AND trade_date >= '2026-06-01' AND trade_date <= '2026-06-30'
    ORDER BY trade_date
""")
for r in cursor.fetchall():
    print(f"  {r[0]}")

print("\n=== AG.SHF 2026-07 数据库日期 ===")
cursor.execute("""
    SELECT DATE(trade_date)::date
    FROM fut_daily_data
    WHERE ts_code = 'AG.SHF' AND period = 'D'
      AND trade_date >= '2026-07-01'
    ORDER BY trade_date
""")
for r in cursor.fetchall():
    print(f"  {r[0]}")

conn.close()
