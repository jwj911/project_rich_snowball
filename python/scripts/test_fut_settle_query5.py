"""验证 fut_settle 的 offset_today_fee 字段和不同交易所数据覆盖情况。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TUSHARE_TOKEN

if not TUSHARE_TOKEN or TUSHARE_TOKEN == "your-tushare-token-here":
    print("[ERROR] TUSHARE_TOKEN 未配置")
    sys.exit(1)

import tushare as ts

ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

print("=== 验证 offset_today_fee 是否存在 ===")
df = pro.fut_settle(trade_date="20250507", exchange="SHFE")
print(f"  字段列表: {list(df.columns)}")
print(f"  offset_today_fee in columns: {'offset_today_fee' in df.columns}")

print("\n=== 验证不同交易所数据覆盖（20250507） ===")
for ex in ["SHFE", "DCE", "CZCE", "INE", "CFFEX", "GFEX"]:
    df = pro.fut_settle(trade_date="20250507", exchange=ex)
    count = len(df) if df is not None else 0
    print(f"  {ex:6s} => {count:4d} 条")

print("\n=== 验证 ts_code 查询历史数据 ===")
df = pro.fut_settle(ts_code="AU2506.SHF")
print(f"  AU2506.SHF 历史结算数据: {len(df)} 条")
if df is not None and len(df) > 0:
    print(f"  日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
