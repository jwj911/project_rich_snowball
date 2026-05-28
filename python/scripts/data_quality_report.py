#!/usr/bin/env python3
"""数据质量检查脚本。

检测内容：
- K 线缺失交易日（使用中国期货市场交易日历，区分"节假日无数据"和"交易日缺失"）
- K 线重复键
- OHLC 异常（high < low、open/close 超出 [low, high]、零值、负值）
- 实时行情与最新 K 线收盘价不一致
- 实时行情缺失品种

用法：
    python scripts/data_quality_report.py [--symbol SYMBOL] [--period PERIOD] [--output json|csv]
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import joinedload

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_URL
from models import (
    CommentDB,
    KlineDataDB,
    PriceLevelDB,
    RealtimeQuoteDB,
    SessionLocal,
    VarietyDB,
    WatchlistDB,
)
from services.trading_calendar import get_expected_kline_dates


MOJIBAKE_MARKERS = ("�", "锟", "鍓", "Ã")


def check_missing_kline_dates(db, symbol: str = None, period: str = "D", lookback_days: int = 30):
    """检查最近 N 个交易日内是否有缺失的 K 线日期。

    使用中国期货市场交易日历，区分"节假日无数据"（正常）和"交易日缺失"（异常）。
    """
    varieties = db.query(VarietyDB)
    if symbol:
        varieties = varieties.filter(VarietyDB.symbol == symbol)
    varieties = varieties.all()

    issues = []
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=lookback_days)

    for v in varieties:
        rows = (
            db.query(KlineDataDB)
            .filter(
                KlineDataDB.variety_id == v.id,
                KlineDataDB.period == period,
                KlineDataDB.trading_time >= start,
                KlineDataDB.trading_time <= end,
            )
            .all()
        )
        actual_dates = {r.trading_time.date() for r in rows}
        expected_dates = get_expected_kline_dates(start, end, period)
        missing = sorted([d for d in expected_dates if d not in actual_dates])
        if missing:
            issues.append({
                "check": "missing_dates",
                "symbol": v.symbol,
                "period": period,
                "missing_count": len(missing),
                "expected_trading_days": len(expected_dates),
                "actual_days": len(actual_dates),
                "missing_sample": [str(m) for m in missing[:5]],
            })

    return issues


def check_duplicate_klines(db, symbol: str = None, period: str = "D"):
    """检查 K 线是否有重复键。"""
    from sqlalchemy import func

    query = db.query(
        KlineDataDB.variety_id,
        KlineDataDB.period,
        KlineDataDB.contract_id,
        KlineDataDB.trading_time,
        func.count().label("cnt")
    ).group_by(
        KlineDataDB.variety_id,
        KlineDataDB.period,
        KlineDataDB.contract_id,
        KlineDataDB.trading_time
    ).having(func.count() > 1)

    if symbol:
        v = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        if v:
            query = query.filter(KlineDataDB.variety_id == v.id)
        else:
            return []
    if period:
        query = query.filter(KlineDataDB.period == period)

    duplicates = query.limit(50).all()
    issues = []
    for d in duplicates:
        v = db.query(VarietyDB).filter(VarietyDB.id == d.variety_id).first()
        issues.append({
            "check": "duplicate_keys",
            "symbol": v.symbol if v else d.variety_id,
            "period": d.period,
            "trading_time": d.trading_time.isoformat() if d.trading_time else None,
            "duplicate_count": d.cnt,
        })
    return issues


def check_ohlc_anomalies(db, symbol: str = None, period: str = None):
    """检查 OHLC 异常值。

    校验规则：
    1. high >= max(open, close, low)
    2. low <= min(open, close, high)
    3. high > 0, low > 0, open > 0, close > 0
    4. volume >= 0
    """
    from sqlalchemy import or_, and_

    query = db.query(KlineDataDB).filter(
        or_(
            KlineDataDB.high_price < KlineDataDB.low_price,
            KlineDataDB.high_price < KlineDataDB.open_price,
            KlineDataDB.high_price < KlineDataDB.close_price,
            KlineDataDB.low_price > KlineDataDB.open_price,
            KlineDataDB.low_price > KlineDataDB.close_price,
            KlineDataDB.high_price <= 0,
            KlineDataDB.low_price <= 0,
            KlineDataDB.open_price <= 0,
            KlineDataDB.close_price <= 0,
        )
    )
    if symbol:
        v = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        if v:
            query = query.filter(KlineDataDB.variety_id == v.id)
    if period:
        query = query.filter(KlineDataDB.period == period)

    bad = query.limit(20).all()
    issues = []
    for r in bad:
        v = db.query(VarietyDB).filter(VarietyDB.id == r.variety_id).first()
        subtype = []
        if r.high_price < r.low_price:
            subtype.append("high_lt_low")
        if r.high_price < max(r.open_price or 0, r.close_price or 0):
            subtype.append("high_below_oc")
        if r.low_price > min(r.open_price or 0, r.close_price or 0):
            subtype.append("low_above_oc")
        if any(x <= 0 for x in [r.open_price, r.high_price, r.low_price, r.close_price]):
            subtype.append("non_positive_price")
        issues.append({
            "check": "ohlc_anomaly",
            "subtype": "|".join(subtype) if subtype else "unknown",
            "symbol": v.symbol if v else r.variety_id,
            "period": r.period,
            "trading_time": r.trading_time.isoformat() if r.trading_time else None,
            "open": r.open_price,
            "high": r.high_price,
            "low": r.low_price,
            "close": r.close_price,
        })

    # 检查成交量为负
    query2 = db.query(KlineDataDB).filter(KlineDataDB.volume < 0)
    if symbol:
        v = db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        if v:
            query2 = query2.filter(KlineDataDB.variety_id == v.id)
    if period:
        query2 = query2.filter(KlineDataDB.period == period)

    bad_vol = query2.limit(20).all()
    for r in bad_vol:
        v = db.query(VarietyDB).filter(VarietyDB.id == r.variety_id).first()
        issues.append({
            "check": "ohlc_anomaly",
            "subtype": "negative_volume",
            "symbol": v.symbol if v else r.variety_id,
            "period": r.period,
            "trading_time": r.trading_time.isoformat() if r.trading_time else None,
            "volume": r.volume,
        })

    return issues


def check_text_encoding_pollution(db, symbol: str = None):
    """检查用户可见中文字段是否包含常见乱码标记。"""

    def polluted(value: str | None) -> bool:
        return isinstance(value, str) and any(marker in value for marker in MOJIBAKE_MARKERS)

    issues = []
    checks = [
        (VarietyDB, "varieties", ("name", "category")),
        (CommentDB, "comments", ("content",)),
        (PriceLevelDB, "price_levels", ("note",)),
        (WatchlistDB, "watchlists", ("notes",)),
    ]

    for model, table, fields in checks:
        rows = db.query(model).limit(10000).all()
        for row in rows:
            if symbol:
                row_symbol = getattr(row, "symbol", None)
                variety = getattr(row, "variety", None)
                product = getattr(row, "product", None)
                row_symbol = row_symbol or getattr(variety, "symbol", None) or getattr(product, "symbol", None)
                if row_symbol != symbol:
                    continue

            for field in fields:
                value = getattr(row, field, None)
                if polluted(value):
                    issues.append({
                        "check": "text_encoding_pollution",
                        "table": table,
                        "field": field,
                        "id": getattr(row, "id", None),
                        "symbol": getattr(row, "symbol", None),
                        "sample": value[:80],
                    })

    return issues


def check_realtime_kline_consistency(db, symbol: str = None):
    """检查实时行情收盘价与最新日线 K 线收盘价是否一致（偏差 < 1%）。"""
    quotes = db.query(RealtimeQuoteDB).options(
        joinedload(RealtimeQuoteDB.variety)
    ).all()

    if symbol:
        quotes = [q for q in quotes if q.variety and q.variety.symbol == symbol]

    issues = []
    for q in quotes:
        v = q.variety
        if not v:
            continue
        latest_kline = (
            db.query(KlineDataDB)
            .filter(
                KlineDataDB.variety_id == v.id,
                KlineDataDB.period == "D",
            )
            .order_by(KlineDataDB.trading_time.desc())
            .first()
        )
        if not latest_kline or not latest_kline.close_price:
            continue

        # 允许 1% 偏差（实时行情与日线收盘价可能因采集时间不同略有差异）
        if q.current_price and abs(q.current_price - latest_kline.close_price) / max(latest_kline.close_price, 0.0001) > 0.01:
            issues.append({
                "check": "realtime_kline_mismatch",
                "symbol": v.symbol,
                "realtime_price": q.current_price,
                "kline_close": latest_kline.close_price,
                "kline_date": latest_kline.trading_time.isoformat() if latest_kline.trading_time else None,
                "deviation_pct": round(abs(q.current_price - latest_kline.close_price) / max(latest_kline.close_price, 0.0001) * 100, 2),
            })

    return issues


def check_missing_realtime(db, symbol: str = None):
    """检查实时行情缺失品种。"""
    varieties = db.query(VarietyDB)
    if symbol:
        varieties = varieties.filter(VarietyDB.symbol == symbol)
    varieties = varieties.all()

    realtime_symbols = {
        r.variety.symbol for r in db.query(RealtimeQuoteDB).options(
            joinedload(RealtimeQuoteDB.variety)
        ).all()
        if r.variety
    }

    issues = []
    for v in varieties:
        if v.symbol not in realtime_symbols:
            issues.append({
                "check": "missing_realtime",
                "symbol": v.symbol,
            })

    return issues


def run_report(args) -> dict:
    db = SessionLocal()
    try:
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "database": DATABASE_URL.split("://")[0] + "://***",
            "filters": {
                "symbol": args.symbol,
                "period": args.period,
            },
            "issues": [],
            "summary": {},
        }

        issues = []
        issues.extend(check_missing_kline_dates(db, args.symbol, args.period, args.lookback))
        issues.extend(check_duplicate_klines(db, args.symbol, args.period))
        issues.extend(check_ohlc_anomalies(db, args.symbol, args.period))
        issues.extend(check_text_encoding_pollution(db, args.symbol))
        issues.extend(check_realtime_kline_consistency(db, args.symbol))
        issues.extend(check_missing_realtime(db, args.symbol))

        report["issues"] = issues
        report["summary"] = {
            "total_issues": len(issues),
            "by_check": defaultdict(int),
        }
        for i in issues:
            report["summary"]["by_check"][i["check"]] += 1

        return report
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="期货数据质量检查报告")
    parser.add_argument("--symbol", help="指定品种 symbol，默认全部")
    parser.add_argument("--period", default="D", help="K 线周期，默认 D")
    parser.add_argument("--lookback", type=int, default=30, help="回溯自然日数，默认 30")
    parser.add_argument("--output", choices=["json", "csv"], default="json", help="输出格式")
    args = parser.parse_args()

    report = run_report(args)

    if args.output == "json":
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        import csv
        writer = csv.writer(sys.stdout)
        writer.writerow(["check", "symbol", "period", "detail"])
        for issue in report["issues"]:
            writer.writerow([
                issue.get("check"),
                issue.get("symbol", ""),
                issue.get("period", ""),
                json.dumps(issue, ensure_ascii=False, default=str),
            ])

    sys.exit(0 if report["summary"]["total_issues"] == 0 else 1)


if __name__ == "__main__":
    main()
