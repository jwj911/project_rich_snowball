"""Tushare 期货数据接入验证脚本。

用法：
    cd python
    set TUSHARE_TOKEN=你的token
    python scripts/verify_tushare.py

脚本会测试以下内容：
1. Tushare Pro API 连接
2. pro_bar 期货分钟数据字段和样本
3. pro_bar 期货日线数据字段和样本
4. fut_basic 合约信息（如权限足够）

根据输出结果，可确认 adapters.py 中的字段映射是否需要调整。
"""
import os
import sys
from pathlib import Path

# 修复 Windows 控制台编码
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 加载 .env 文件（与 config.py 保持一致）
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    token = os.getenv("TUSHARE_TOKEN")
    if not token or token == "your-tushare-token-here":
        print("[ERROR] TUSHARE_TOKEN 未配置。请在 .env 文件中设置，或临时导出环境变量：")
        print("   set TUSHARE_TOKEN=你的token")
        sys.exit(1)

    import tushare as ts
    ts.set_token(token)
    pro = ts.pro_api()

    print("=" * 60)
    print("Tushare 期货数据验证")
    print("=" * 60)

    # 1. 测试期货日线数据（主力合约）
    print("\n[1] 期货日线数据 (fut_daily, 主力合约 AU.SHF)")
    print("-" * 60)
    try:
        df = pro.fut_daily(ts_code="AU.SHF", start_date="20260401", end_date="20260504")
        if df is not None and not df.empty:
            print(f"[OK] 返回 {len(df)} 条数据")
            print(f"列名: {list(df.columns)}")
            print("\n样本数据（最近1条）：")
            print(df.tail(1).to_string(index=False))
        else:
            print("[WARN] 返回空数据（可能是权限不足）")
    except Exception as e:
        print(f"[ERR] 失败: {e}")

    # 2. 测试 pro_bar 期货分钟数据（主力合约）
    print("\n[2] 期货分钟数据 (pro_bar, asset='FT', freq='1min', 主力合约 AU.SHF)")
    print("-" * 60)
    try:
        df = ts.pro_bar(ts_code="AU.SHF", asset="FT", freq="1min", start_date="2026-05-04 09:00:00")
        if df is not None and not df.empty:
            print(f"✅ 返回 {len(df)} 条数据")
            print(f"列名: {list(df.columns)}")
            print("\n样本数据（最近3条）：")
            print(df.tail(3).to_string(index=False))
        else:
            print("⚠️ 返回空数据（可能权限不足，分钟数据通常需要 2000+ 积分）")
    except Exception as e:
        print(f"❌ 失败: {e}")

    # 3. 测试 pro_bar 期货日线数据（主力合约）
    print("\n[3] 期货日线数据 (pro_bar, asset='FT', freq='D', 主力合约 AU.SHF)")
    print("-" * 60)
    try:
        df = ts.pro_bar(ts_code="AU.SHF", asset="FT", freq="D", start_date="20260401")
        if df is not None and not df.empty:
            print(f"✅ 返回 {len(df)} 条数据")
            print(f"列名: {list(df.columns)}")
            print("\n样本数据（最近3条）：")
            print(df.tail(3).to_string(index=False))
        else:
            print("⚠️ 返回空数据")
    except Exception as e:
        print(f"❌ 失败: {e}")

    # 3b. 测试过期具体合约（确认空数据原因）
    print("\n[3b] 期货日线数据 (fut_daily, 过期合约 AU2506.SHF)")
    print("-" * 60)
    try:
        df = pro.fut_daily(ts_code="AU2506.SHF", start_date="20260401", end_date="20260504")
        if df is not None and not df.empty:
            print(f"✅ 返回 {len(df)} 条数据")
        else:
            print("⚠️ 返回空数据 —— 确认：过期合约确实查不到数据")
    except Exception as e:
        print(f"❌ 失败: {e}")

    # 4. 测试 fut_basic 合约信息
    print("\n[4] 期货合约基本信息 (fut_basic)")
    print("-" * 60)
    try:
        df = pro.fut_basic(exchange="SHFE", fut_type="2")
        if df is not None and not df.empty:
            print(f"✅ 返回 {len(df)} 条合约信息")
            print(f"列名: {list(df.columns)}")
            print("\n样本数据（前3条）：")
            print(df.head(3).to_string(index=False))
        else:
            print("⚠️ 返回空数据")
    except Exception as e:
        print(f"❌ 失败: {e}")

    # 5. 汇总建议
    print("\n" + "=" * 60)
    print("验证完成")
    print("=" * 60)
    print("""
下一步建议：
1. 确认 pro_bar 返回的列名是否包含: open, high, low, close, vol, (oi/pre_close)
2. 如果列名不同，请把实际列名告诉我，我调整 adapters.py
3. 如果分钟数据返回空，可能是积分不足，可先用日线数据验证映射逻辑
""")


if __name__ == "__main__":
    main()
