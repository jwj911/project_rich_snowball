"""验证 Tushare fut_settle 接口 ts_code 查询和交易所代码。"""

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

print("=== 测试: 按 ts_code 查询 (AU2506.SHF) ===")
try:
    df = pro.fut_settle(ts_code="AU2506.SHF")
    print(f"  返回 {len(df)} 条" if df is not None else "  返回 None")
    if df is not None and len(df) > 0:
        print(f"  字段: {list(df.columns)}")
        print(f"  示例: {df.iloc[0].to_dict()}")
except Exception as e:
    print(f"  异常: {e}")

print("\n=== 测试: DCE 交易所代码 ===")
for ex in ["DCE", "DLCE", "CED", "CZCE", "ZCE"]:
    try:
        df = pro.fut_settle(trade_date="20250507", exchange=ex)
        print(f"  exchange='{ex}' => {len(df)} 条" if df is not None else f"  exchange='{ex}' => None")
    except Exception as e:
        print(f"  exchange='{ex}' => 异常: {e}")

print("\n=== 测试: SHFE 不同日期 ===")
for date in ["20250506", "20250507", "20250508"]:
    try:
        df = pro.fut_settle(trade_date=date, exchange="SHFE")
        print(f"  {date} => {len(df)} 条" if df is not None else f"  {date} => None")
    except Exception as e:
        print(f"  {date} => 异常: {e}")

print("\n=== 测试: trade_date + start_date/end_date (必须有 trade_date) ===")
try:
    df = pro.fut_settle(trade_date="20250507", start_date="20250506", end_date="20250508")
    print(f"  trade_date + start/end => {len(df)} 条" if df is not None else "  => None")
    if df is not None and len(df) > 0:
        print(f"  日期分布: {sorted(df['trade_date'].unique().tolist())}")
except Exception as e:
    print(f"  异常: {e}")
