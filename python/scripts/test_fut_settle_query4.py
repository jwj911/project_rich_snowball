"""验证 fut_settle 返回字段，特别是 exchange 字段是否存在。"""

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

print("=== 指定 exchange=SHFE 时的字段 ===")
df = pro.fut_settle(trade_date="20250507", exchange="SHFE")
print(f"  返回 {len(df)} 条")
print(f"  字段: {list(df.columns)}")
if 'exchange' in df.columns:
    print(f"  exchange 示例值: {df['exchange'].iloc[0]}")
else:
    print("  ⚠️ 没有 exchange 字段！")

print("\n=== 不指定 exchange 时的字段 ===")
df = pro.fut_settle(trade_date="20250507")
print(f"  返回 {len(df)} 条")
print(f"  字段: {list(df.columns)}")
if 'exchange' in df.columns:
    print(f"  exchange 示例值: {df['exchange'].iloc[0]}")
else:
    print("  ⚠️ 没有 exchange 字段！")

print("\n=== 验证 DCE 是否真的没有数据（换日期） ===")
for date in ["20250506", "20250507", "20250508"]:
    df = pro.fut_settle(trade_date=date, exchange="DCE")
    print(f"  DCE {date} => {len(df)} 条")

print("\n=== 验证 CZCE 是否真的没有数据（换日期） ===")
for date in ["20250506", "20250507", "20250508"]:
    df = pro.fut_settle(trade_date=date, exchange="CZCE")
    print(f"  CZCE {date} => {len(df)} 条")

print("\n=== 验证 CFFEX 是否真的没有数据 ===")
for date in ["20250506", "20250507", "20250508"]:
    df = pro.fut_settle(trade_date=date, exchange="CFFEX")
    print(f"  CFFEX {date} => {len(df)} 条")
