"""九期网期货手续费与保证金数据拉取脚本

来源: AKShare futures_comm_info 接口 (数据来自 www.9qihuo.com)
支持按交易所拉取或一次性拉取全部，保存 CSV 并可选写入 PostgreSQL/SQLite。

用法:
    # 拉取所有交易所，仅保存 CSV
    python tushare_pg_ingest/ingest_commission_9qihuo.py

    # 拉取指定交易所
    python tushare_pg_ingest/ingest_commission_9qihuo.py --exchange "上海期货交易所"

    # 全量拉取 + 写入数据库（默认 PostgreSQL）
    python tushare_pg_ingest/ingest_commission_9qihuo.py --save-db --allow-sqlite

    # 仅主力合约 + 更新 varieties 表 + 写入 fut_trade_fee
    python tushare_pg_ingest/ingest_commission_9qihuo.py --main-only --save-db --update-varieties --allow-sqlite

    # 指定输出目录
    python tushare_pg_ingest/ingest_commission_9qihuo.py --output-dir ./data/commission
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# 复用 common 里的项目根目录定位与环境加载
ROOT = Path(__file__).resolve().parents[2]
PYTHON_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PYTHON_DIR))

from common import configure_database, print_stats, IngestStats, records_from_df

import akshare as ak
import pandas as pd


EXCHANGE_CHOICES = [
    "所有",
    "上海期货交易所",
    "大连商品交易所",
    "郑州商品交易所",
    "上海国际能源交易中心",
    "中国金融期货交易所",
    "广州期货交易所",
]

# 交易所名称 -> 代码映射（用于关联 varieties 表）
EXCHANGE_NAME_TO_CODE = {
    "上海期货交易所": "SHFE",
    "大连商品交易所": "DCE",
    "郑州商品交易所": "CZCE",
    "上海国际能源交易中心": "INE",
    "中国金融期货交易所": "CFFEX",
    "广州期货交易所": "GFEX",
}

# AKShare 原始字段 -> 模型字段映射
COLUMN_MAP = {
    "交易所名称": "exchange",
    "合约名称": "contract_name",
    "合约代码": "contract_code",
    "现价": "current_price",
    "涨停板": "up_limit",
    "跌停板": "down_limit",
    "保证金-买开": "margin_buy_open",
    "保证金-卖开": "margin_sell_open",
    "保证金-每手": "margin_per_hand",
    "手续费标准-开仓-万分之": "fee_open_rate",
    "手续费标准-开仓-元": "fee_open_fixed",
    "手续费标准-平昨-万分之": "fee_close_yesterday_rate",
    "手续费标准-平昨-元": "fee_close_yesterday_fixed",
    "手续费标准-平今-万分之": "fee_close_today_rate",
    "手续费标准-平今-元": "fee_close_today_fixed",
    "每跳毛利": "tick_profit_gross",
    "手续费": "fee_total",
    "每跳净利": "tick_profit_net",
    "备注": "remark",
    "手续费更新时间": "fee_updated_at",
    "价格更新时间": "price_updated_at",
}


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>| ]+', "_", name).strip("_")


def _parse_datetime(value: Any) -> datetime | None:
    """解析九期网返回的时间字符串。"""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    s = str(value).strip()
    if not s or s == "nan":
        return None
    # 常见格式: 2026-05-08 22:35:28.051
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _to_float(value: Any) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def fetch_commission_data(exchange: str = "所有", max_retries: int = 3) -> pd.DataFrame:
    """通过 AKShare 拉取九期网手续费数据，支持失败重试。"""
    if exchange not in EXCHANGE_CHOICES:
        raise ValueError(f"不支持的交易所: {exchange}")

    print(f"[FETCH] 正在拉取 [{exchange}] 数据...")
    last_exc = None
    for attempt in range(max_retries):
        try:
            df = ak.futures_comm_info(symbol=exchange)
            print(f"[FETCH]   记录数: {len(df)}")
            return df
        except Exception as e:
            last_exc = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                print(f"[RETRY {attempt + 1}/{max_retries}] 拉取失败，{wait}s 后重试: {e}")
                time.sleep(wait)
    raise last_exc


def extract_symbol_from_contract(contract_name: str, contract_code: str) -> str:
    """从合约名称或合约代码中提取品种代码（字母部分）。

    例: '沪银2606 (ag2606)' -> 'AG'
         '30年期国债期货2409' -> 'TL'
    """
    letters = "".join(ch for ch in contract_code if ch.isalpha()).upper()
    if letters:
        return letters

    cn_to_symbol = {
        "白银": "AG", "黄金": "AU", "沪锡": "SN", "沪镍": "NI", "沪铜": "CU",
        "沪铝": "AL", "沪锌": "ZN", "沪铅": "PB", "氧化铝": "AO", "线材": "WR",
        "不锈钢": "SS", "铸造铝": "AD", "螺纹钢": "RB", "热卷": "HC",
        "沥青": "BU", "燃油": "FU", "合成橡胶": "BR", "橡胶": "RU",
        "纸浆": "SP", "胶版纸": "OP",
        "原油": "SC", "低硫燃料油": "LU", "20号胶": "NR", "集运指数": "EC", "国际铜": "BC",
        "碳酸锂": "LC", "多晶硅": "PS", "工业硅": "SI", "钯": "PD", "铂": "PT",
        "2年期国债": "TS", "5年期国债": "TF", "10年国债": "T", "30年期国债": "TL",
        "沪深300指数": "IF", "中证500股指": "IC", "上证50指数": "IH", "中证1000股指": "IM",
        "豆油": "Y", "棕榈油": "P", "豆一": "A", "豆二": "B", "豆粕": "M",
        "玉米": "C", "玉米淀粉": "CS", "粳米": "RR", "生猪": "LH", "鸡蛋": "JD",
        "铁矿石": "I", "焦炭": "J", "焦煤": "JM", "液化石油气": "PG",
        "聚丙烯": "PP", "塑料": "L", "PVC": "V", "乙二醇": "EG", "苯乙烯": "EB",
        "纯苯": "BZ", "纤维板": "FB", "原木": "LG", "胶板": "BB",
        "油菜籽": "RS", "菜籽油": "OI", "菜籽粕": "RM", "花生": "PK",
        "粳稻": "JR", "郑麦": "WH", "小麦": "PM", "早籼稻": "RI",
        "白糖": "SR", "棉花": "CF", "红枣": "CJ", "苹果": "AP", "棉纱": "CY",
        "锰硅": "SM", "硅铁": "SF", "动力煤": "ZC", "丙烯": "PL",
        "对二甲苯": "PX", "PTA": "TA", "短纤": "PF", "瓶片": "PR",
        "甲醇": "MA", "尿素": "UR", "烧碱": "SH", "纯碱": "SA", "玻璃": "FG",
    }
    for cn, sym in cn_to_symbol.items():
        if cn in contract_name:
            return sym
    return ""


def df_to_model_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """将 DataFrame 转换为 FutTradeFeeDB 可接受的字典列表。"""
    records = []
    for _, row in df.iterrows():
        rec: dict[str, Any] = {}
        for src_col, dst_col in COLUMN_MAP.items():
            val = row.get(src_col)
            if dst_col in ("current_price", "up_limit", "down_limit",
                           "margin_buy_open", "margin_sell_open",
                           "fee_open_rate", "fee_close_yesterday_rate", "fee_close_today_rate",
                           "fee_total", "tick_profit_net"):
                rec[dst_col] = _to_float(val)
            elif dst_col in ("tick_profit_gross",):
                rec[dst_col] = _to_int(val)
            elif dst_col in ("margin_per_hand",):
                rec[dst_col] = _to_float(val)
            elif dst_col in ("fee_updated_at", "price_updated_at"):
                rec[dst_col] = _parse_datetime(val)
            else:
                rec[dst_col] = None if (isinstance(val, float) and math.isnan(val)) else str(val) if val is not None else None
        records.append(rec)
    return records


def save_csv(df: pd.DataFrame, output_dir: Path, suffix: str = "") -> Path:
    """保存 DataFrame 为 CSV。"""
    _ensure_dir(output_dir)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = f"futures_comm_{_safe_filename(suffix)}_{ts}.csv"
    path = output_dir / name
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"[SAVE] CSV 已保存: {path}")
    return path


def bulk_save_to_db(db: Any, rows: list[dict[str, Any]], dry_run: bool) -> int:
    """批量写入/更新 fut_trade_fee 表。"""
    if not rows:
        return 0

    from models import FutTradeFeeDB, engine
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    dialect_insert = pg_insert if engine.dialect.name == "postgresql" else sqlite_insert

    stmt = dialect_insert(FutTradeFeeDB).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["contract_code", "fee_updated_at"],
        set_={
            "exchange": stmt.excluded.exchange,
            "contract_name": stmt.excluded.contract_name,
            "current_price": stmt.excluded.current_price,
            "up_limit": stmt.excluded.up_limit,
            "down_limit": stmt.excluded.down_limit,
            "margin_buy_open": stmt.excluded.margin_buy_open,
            "margin_sell_open": stmt.excluded.margin_sell_open,
            "margin_per_hand": stmt.excluded.margin_per_hand,
            "fee_open_rate": stmt.excluded.fee_open_rate,
            "fee_open_fixed": stmt.excluded.fee_open_fixed,
            "fee_close_yesterday_rate": stmt.excluded.fee_close_yesterday_rate,
            "fee_close_yesterday_fixed": stmt.excluded.fee_close_yesterday_fixed,
            "fee_close_today_rate": stmt.excluded.fee_close_today_rate,
            "fee_close_today_fixed": stmt.excluded.fee_close_today_fixed,
            "tick_profit_gross": stmt.excluded.tick_profit_gross,
            "fee_total": stmt.excluded.fee_total,
            "tick_profit_net": stmt.excluded.tick_profit_net,
            "remark": stmt.excluded.remark,
            "price_updated_at": stmt.excluded.price_updated_at,
            "created_at": datetime.now(),
        },
    )

    if dry_run:
        print(f"[DRY] 将写入/更新 fut_trade_fee {len(rows)} 条")
        return len(rows)

    result = db.execute(stmt)
    count = result.rowcount if hasattr(result, "rowcount") else len(rows)
    print(f"[OK] fut_trade_fee 写入/更新 {count} 条")
    return count


def update_varieties_from_main(df: pd.DataFrame, db: Any, dry_run: bool) -> IngestStats:
    """将主力合约的手续费/保证金率写回 varieties 表。"""
    stats = IngestStats()
    from models import VarietyDB

    main_df = df[df["备注"].astype(str).str.contains("主力", na=False)]
    print(f"[UPDATE] 主力合约数: {len(main_df)}")

    for _, row in main_df.iterrows():
        exchange_name = str(row.get("交易所名称", ""))
        exchange = EXCHANGE_NAME_TO_CODE.get(exchange_name)
        contract_code = str(row.get("合约代码", ""))
        symbol = extract_symbol_from_contract(str(row.get("合约名称", "")), contract_code)

        if not symbol or not exchange:
            stats.skipped += 1
            continue

        variety = db.query(VarietyDB).filter(
            VarietyDB.symbol == symbol,
            VarietyDB.exchange == exchange,
        ).first()

        if not variety:
            stats.skipped += 1
            continue

        try:
            margin_val = float(row.get("保证金-买开", 0))
            if margin_val > 0:
                variety.margin_rate = margin_val / 100
        except (ValueError, TypeError):
            pass

        try:
            comm_str = str(row.get("手续费", "0")).replace("元", "").strip()
            comm_val = float(comm_str)
            variety.commission = comm_val
        except (ValueError, TypeError):
            pass

        stats.written += 1

    if dry_run:
        db.rollback()
        print(f"[DRY] varieties 将更新 {stats.written} 条，跳过 {stats.skipped} 条")
    else:
        db.commit()
        print(f"[OK] varieties 已更新 {stats.written} 条，跳过 {stats.skipped} 条")

    return stats


def print_summary(df: pd.DataFrame, title: str = "数据汇总") -> None:
    """打印数据摘要。"""
    print(f"\n{'=' * 60}")
    print(f"[{title}]")
    print(f"{'=' * 60}")
    print(f"总记录数: {len(df)}")
    if "交易所名称" in df.columns:
        print(f"交易所分布:")
        for ex, cnt in df["交易所名称"].value_counts().items():
            print(f"   {ex}: {cnt} 条")
    if "备注" in df.columns:
        main_cnt = df["备注"].astype(str).str.contains("主力", na=False).sum()
        print(f"主力合约数: {main_cnt}")
    print(f"\n字段列表 ({len(df.columns)} 个):")
    for i, col in enumerate(df.columns, 1):
        print(f"   {i}. {col}")


def print_main_contracts(df: pd.DataFrame, top_n: int | None = None) -> None:
    """打印主力合约明细。"""
    main_df = df[df["备注"].astype(str).str.contains("主力", na=False)]
    if main_df.empty:
        print("\n[WARN] 未找到主力合约")
        return

    display = main_df if top_n is None else main_df.head(top_n)
    print(f"\n{'-' * 80}")
    print(f"主力合约明细 ({len(display)} / {len(main_df)}):")
    print(f"{'-' * 80}")
    for _, row in display.iterrows():
        print(
            f"   {row['合约名称']} ({row['合约代码']}) | "
            f"保证金/手: {row.get('保证金-每手', '-')} | "
            f"手续费(开+平): {row.get('手续费', '-')} | "
            f"每跳净利: {row.get('每跳净利', '-')}"
        )


def ingest(args: argparse.Namespace) -> IngestStats:
    """主入口。"""
    output_dir = Path(args.output_dir)
    _ensure_dir(output_dir)

    stats = IngestStats()
    all_data: list[pd.DataFrame] = []

    # 1. 拉取数据
    if args.exchange == "所有":
        exchanges = [e for e in EXCHANGE_CHOICES if e != "所有"]
    else:
        exchanges = [args.exchange]

    for ex in exchanges:
        try:
            df = fetch_commission_data(exchange=ex)
            stats.fetched += len(df)
            all_data.append(df)

            if args.save_per_exchange:
                save_csv(df, output_dir, suffix=ex)
        except Exception as e:
            print(f"[ERROR] 拉取 {ex} 失败: {e}")
            stats.failed += 1

    if not all_data:
        print("[ERROR] 未获取到任何数据")
        return stats

    combined = pd.concat(all_data, ignore_index=True)

    # 2. 可选：仅保留主力合约
    if args.main_only:
        combined = combined[combined["备注"].astype(str).str.contains("主力", na=False)]
        print(f"[FILTER] 主力合约筛选后: {len(combined)} 条")

    # 3. 保存合并 CSV
    suffix = "main" if args.main_only else "all"
    save_csv(combined, output_dir, suffix=suffix)

    # 4. 打印摘要
    print_summary(combined, title="九期网手续费数据汇总")
    if args.show_main:
        print_main_contracts(combined, top_n=args.top_n)

    # 5. 数据库操作
    if args.save_db or args.update_varieties:
        configure_database(allow_sqlite=args.allow_sqlite)
        from models import SessionLocal

        db = SessionLocal()
        try:
            # 5a. 写入 fut_trade_fee
            if args.save_db:
                rows = df_to_model_records(combined)
                written = bulk_save_to_db(db, rows, dry_run=args.dry_run)
                stats.written += written
                if not args.dry_run:
                    db.commit()

            # 5b. 更新 varieties 表
            if args.update_varieties:
                update_stats = update_varieties_from_main(
                    combined,
                    db,
                    dry_run=args.dry_run,
                )
                stats.add(update_stats)
        finally:
            db.close()

    return stats


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--exchange",
        default="所有",
        help=f"交易所名称; 默认 '所有'. 可选: {', '.join(EXCHANGE_CHOICES)}",
    )
    parser.add_argument("--output-dir", default="./data/commission", help="CSV 输出目录")
    parser.add_argument("--save-per-exchange", action="store_true", help="每个交易所单独存一份 CSV")
    parser.add_argument("--main-only", action="store_true", help="仅保留主力合约")
    parser.add_argument("--show-main", action="store_true", help="打印主力合约明细")
    parser.add_argument("--top-n", type=int, help="打印主力合约明细时仅显示前 N 条")
    parser.add_argument("--save-db", action="store_true", help="将数据写入 fut_trade_fee 表")
    parser.add_argument("--update-varieties", action="store_true", help="将主力合约费率更新到 varieties 表")
    parser.add_argument("--allow-sqlite", action="store_true", help="允许写入 SQLite（仅数据库操作时生效）")
    parser.add_argument("--dry-run", action="store_true", help="模拟操作，不提交数据库")
    return parser


def main() -> int:
    stats = ingest(build_parser().parse_args())
    print_stats("9qihuo commission", stats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
