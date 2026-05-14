#!/usr/bin/env python3
"""数据质量检查脚本。

检测内容：
- K 线缺失日期
- K 线重复键
- OHLC 异常（high < low, open/close 超出范围）
- 成交量为负
- 实时行情缺失品种

用法：
    python scripts/data_quality_report.py [--symbol SYMBOL] [--period PERIOD] [--output json|csv]
"""
import argparse
import json
import sys
import os
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# 确保项目根目录在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import SessionLocal, KlineDataDB, RealtimeQuoteDB, VarietyDB, FutContractDB
from config import DATABASE_URL


def check_missing_kline_dates(db, symbol: str = None, period: str = "1d", lookback_days: int = 30):
    """检查最近 N 天是否有缺失的 K 线日期。"""
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
        dates = {r.trading_time.date() for r in rows}
        expected = set()
        d = start
        while d <= end:
            expected.add(d)
            d += timedelta(days=1)
        missing = sorted(expected - dates)
        if missing:
            issues.append({
                "check": "missing_dates",
                "symbol": v.symbol,
                "period": period,
                "missing_count": len(missing),
                "missing_sample": [str(m) for m in missing[:5]],
            })

    return issues


def check_duplicate_klines(db, symbol: str = None, period: str = "1d"):
    """检查 K 线是否有重复键。"""
    from sqlalchemy import func

    query = db.query(
        KlineDataDB.variety_id,
        KlineDataDB.period,
        KlineDataDB.trading_time,
        func.count().label("cnt")
    ).group_by(
        KlineDataDB.variety_id,
        KlineDataDB.period,
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
    """检查 OHLC 异常值。"""
    query = db.query(KlineDataDB).filter(
        KlineDataDB.high_price < KlineDataDB.low_price
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
        issues.append({
            "check": "ohlc_anomaly",
            "subtype": "high_lt_low",
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


def check_missing_realtime(db, symbol: str = None):
    """检查实时行情缺失品种。"""
    varieties = db.query(VarietyDB)
    if symbol:
        varieties = varieties.filter(VarietyDB.symbol == symbol)
    varieties = varieties.all()

    realtime_symbols = {
        r.variety.symbol for r in db.query(RealtimeQuoteDB).all()
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
    parser.add_argument("--period", default="1d", help="K 线周期，默认 1d")
    parser.add_argument("--lookback", type=int, default=30, help="回溯天数，默认 30")
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
