"""验证 Tushare fut_wsr 接口 symbol 参数格式。

测试场景：
1. 品种简称（如 AU、ZN、CU）
2. 主连代码（如 AU.SHF、ZN.SHF）
3. 不指定 symbol，按日期全量拉取

运行方式：
    cd python
    python scripts/test_fut_wsr_symbol.py
"""

import os
import sys

# 确保能加载项目根目录的 .env 和 config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import TUSHARE_TOKEN

if not TUSHARE_TOKEN or TUSHARE_TOKEN == "your-tushare-token-here":
    print("[ERROR] TUSHARE_TOKEN 未配置")
    sys.exit(1)

import tushare as ts

ts.set_token(TUSHARE_TOKEN)
pro = ts.pro_api()

# 使用一个已知的交易日进行测试（尽量选近期交易日）
TEST_DATE = "20250507"

# 要测试的 symbol 候选
test_cases = [
    ("品种简称", "AU"),      # 黄金品种简称
    ("品种简称", "ZN"),      # 锌品种简称
    ("品种简称", "CU"),      # 铜品种简称
    ("主连代码", "AU.SHF"),  # 黄金主连
    ("主连代码", "ZN.SHF"),  # 锌主连
    ("主连代码", "CU.SHF"),  # 铜主连
]

print(f"=== Tushare fut_wsr symbol 格式验证 (trade_date={TEST_DATE}) ===\n")

for desc, symbol in test_cases:
    try:
        df = pro.fut_wsr(trade_date=TEST_DATE, symbol=symbol)
        count = len(df) if df is not None else 0
        print(f"[{desc:6s}] symbol={symbol:10s} => 返回 {count:3d} 条")
        if count > 0:
            # 打印第一条看看字段
            row = df.iloc[0].to_dict()
            print(f"         示例: {row.get('symbol')} | {row.get('fut_name')} | {row.get('warehouse')} | vol={row.get('vol')}")
    except Exception as e:
        print(f"[{desc:6s}] symbol={symbol:10s} => 异常: {e}")

print("\n=== 不指定 symbol，按日期全量拉取 ===")
try:
    df = pro.fut_wsr(trade_date=TEST_DATE)
    count = len(df) if df is not None else 0
    print(f"[全量] 不指定 symbol => 返回 {count} 条")
    if count > 0:
        # 看看涉及哪些品种
        symbols = df["symbol"].unique().tolist() if "symbol" in df.columns else []
        print(f"       涉及品种: {symbols[:20]}{'...' if len(symbols) > 20 else ''}")
        row = df.iloc[0].to_dict()
        print(f"       示例: {row.get('symbol')} | {row.get('fut_name')} | {row.get('warehouse')} | vol={row.get('vol')}")
except Exception as e:
    print(f"[全量] 异常: {e}")

print("\n=== 结论 ===")
print("如果 '品种简称' 有数据而 '主连代码' 无数据，则 symbol 应使用品种简称（如 AU、ZN）。")
print("如果两者都有数据，则优先使用品种简称（与文档示例一致）。")
