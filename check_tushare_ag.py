import os, sys
from pathlib import Path
from datetime import date, timedelta

root = Path(__file__).parent
sys.path.insert(0, str(root / 'python'))
sys.path.insert(0, str(root / 'python' / 'tushare_pg_ingest'))

from dotenv import load_dotenv
load_dotenv(dotenv_path=root / '.env')

import tushare as ts
ts.set_token(os.getenv('TUSHARE_TOKEN'))
pro = ts.pro_api()

print("=== 检查 Tushare 上 AG.SHF 各月数据完整性 ===\n")

# 按月查询
for month_start in ['20260501', '20260601', '20260701']:
    # 计算月末
    y, m = int(month_start[:4]), int(month_start[4:6])
    if m == 12:
        next_month = date(y+1, 1, 1)
    else:
        next_month = date(y, m+1, 1)
    month_end = (next_month - timedelta(days=1)).strftime('%Y%m%d')

    df = pro.fut_daily(ts_code='AG.SHF', start_date=month_start, end_date=month_end)
    if df is None or df.empty:
        print(f"{month_start[:6]}: 无数据")
        continue

    dates = sorted(df['trade_date'].tolist())
    print(f"{month_start[:6]}: 返回 {len(dates)} 条")

    # 列出该月应有的交易日（简单估算）
    expected = []
    d = date(y, m, 1)
    while d.month == m:
        if d.weekday() < 5:
            # 粗略：不算具体节假日，只算工作日
            expected.append(d.strftime('%Y%m%d'))
        d += timedelta(days=1)

    missing = [d for d in expected if d not in dates]
    print(f"  工作日总数: {len(expected)}")
    print(f"  缺失工作日: {len(missing)}")
    if missing:
        print(f"  缺失日期: {', '.join(missing)}")
    print()

# 重点检查 2026-06-10 到 2026-06-28
print("=== 重点检查 2026-06-10 ~ 2026-06-28 ===")
df = pro.fut_daily(ts_code='AG.SHF', start_date='20260610', end_date='20260628')
if df is not None and not df.empty:
    dates = sorted(df['trade_date'].tolist())
    print(f"返回 {len(dates)} 条: {dates}")
else:
    print("无数据")
