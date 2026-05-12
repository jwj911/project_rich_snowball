"""验证 Tushare fut_settle 接口不同查询方式的返回量。"""

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

print("=== 测试1: 单日期 + 单交易所 (SHFE) ===")
df = pro.fut_settle(trade_date="20250507", exchange="SHFE")
print(f"  返回 {len(df)} 条" if df is not None else "  返回 None")

print("\n=== 测试2: 单日期 + 单交易所 (DCE) ===")
df = pro.fut_settle(trade_date="20250507", exchange="DCE")
print(f"  返回 {len(df)} 条" if df is not None else "  返回 None")

print("\n=== 测试3: 日期范围 + 单交易所 (SHFE, 3天) ===")
df = pro.fut_settle(exchange="SHFE", start_date="20250506", end_date="20250508")
print(f"  返回 {len(df)} 条" if df is not None else "  返回 None")
if df is not None and len(df) > 0:
    print(f"  日期分布: {sorted(df['trade_date'].unique().tolist())}")

print("\n=== 测试4: 日期范围 + 单交易所 (SHFE, 10天) ===")
df = pro.fut_settle(exchange="SHFE", start_date="20250428", end_date="20250507")
print(f"  返回 {len(df)} 条" if df is not None else "  返回 None")

print("\n=== 测试5: 日期范围 + 无交易所 (3天) ===")
df = pro.fut_settle(start_date="20250506", end_date="20250508")
print(f"  返回 {len(df)} 条" if df is not None else "  返回 None")
if df is not None and len(df) > 0:
    print(f"  交易所分布: {df['exchange'].value_counts().to_dict()}")

print("\n=== 测试6: 按 ts_code 查询 ===")
df = pro.fut_settle(ts_code="AU2506.SHF")
print(f"  返回 {len(df)} 条" if df is not None else "  返回 None")
if df is not None and len(df) > 0:
    print(f"  字段: {list(df.columns)}")
    print(f"  示例: {df.iloc[0].to_dict()}")

print("\n=== 结论 ===")
print("如果 测试3/4 有数据，说明 start_date/end_date + exchange 组合可用，可以大幅优化 ingest_settle.py")
print("如果 测试6 有数据，说明支持按 ts_code 查询，可增加 --ts-code 参数")
