"""进一步验证 fut_settle 的交易所代码和 start_date/end_date 行为。"""

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

print("=== 测试: 各交易所 20250507 返回量 ===")
for ex in ["SHFE", "DCE", "CZCE", "ZCE", "INE", "CFFEX", "GFEX"]:
    try:
        df = pro.fut_settle(trade_date="20250507", exchange=ex)
        count = len(df) if df is not None else 0
        print(f"  {ex:6s} => {count:4d} 条")
    except Exception as e:
        print(f"  {ex:6s} => 异常: {e}")

print("\n=== 测试: trade_date=20250507 不加 exchange ===")
df = pro.fut_settle(trade_date="20250507")
print(f"  返回 {len(df)} 条" if df is not None else "  返回 None")
if df is not None and len(df) > 0:
    print(f"  交易所分布:")
    for ex, cnt in df['exchange'].value_counts().items():
        print(f"    {ex}: {cnt}")

print("\n=== 测试: start_date/end_date 不加 trade_date/ts_code (应该报错) ===")
try:
    df = pro.fut_settle(start_date="20250506", end_date="20250508")
    print(f"  返回 {len(df)} 条")
except Exception as e:
    print(f"  异常(预期): {e}")

print("\n=== 测试: ts_code + start_date/end_date ===")
try:
    df = pro.fut_settle(ts_code="AU2506.SHF", start_date="20250501", end_date="20250507")
    print(f"  返回 {len(df)} 条" if df is not None else "  返回 None")
    if df is not None and len(df) > 0:
        print(f"  日期范围: {df['trade_date'].min()} ~ {df['trade_date'].max()}")
        print(f"  唯一日期数: {df['trade_date'].nunique()}")
except Exception as e:
    print(f"  异常: {e}")
