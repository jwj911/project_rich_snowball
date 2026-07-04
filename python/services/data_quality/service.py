"""数据质量服务入口。"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from models import KlineDataDB, RealtimeQuoteDB, VarietyDB
from services.agent.utils import resolve_symbol
from services.data_quality.checks import check_daily_date_gaps, check_kline_duplicates, check_kline_ohlc
from services.data_quality.coverage import get_kline_coverage, get_realtime_coverage
from services.data_quality.scoring import score_issues
from services.data_quality.types import DataQualityIssue, DataQualityReport


class DataQualityService:
    """面向 Agent 和路由的数据质量检查服务。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def inspect(self, query: str, symbol: str | None = None, period: str | None = None) -> DataQualityReport:
        """根据查询意图执行数据质量检查。"""
        resolved_symbol = (symbol or resolve_symbol(self.db, query) or "").upper() or None
        resolved_period = period or _resolve_period(query)

        if _looks_like_inventory_query(query) and not resolved_symbol:
            return self.inventory()
        if _looks_like_realtime_query(query) and not _looks_like_kline_query(query):
            return self.check_realtime(resolved_symbol)
        if resolved_symbol:
            return self.check_kline(resolved_symbol, resolved_period)

        return self.inventory()

    def inventory(self) -> DataQualityReport:
        """返回第一版数据资产盘点摘要。"""
        variety_count = self.db.query(VarietyDB).count()
        kline_coverage = self._dataset_summary("kline_data")
        realtime_coverage = get_realtime_coverage(self.db)
        realtime_count = realtime_coverage["row_count"]

        issues: list[DataQualityIssue] = []
        if variety_count == 0:
            issues.append(DataQualityIssue("bad", "VARIETY_EMPTY", "品种表为空，Agent 无法解析品种"))
        if kline_coverage["row_count"] == 0:
            issues.append(DataQualityIssue("warning", "KLINE_EMPTY", "K 线表暂无数据"))
        if realtime_count == 0:
            issues.append(DataQualityIssue("warning", "REALTIME_EMPTY", "实时行情表暂无数据"))

        status, score = score_issues(issues)
        datasets = [
            {
                "dataset_name": "varieties",
                "label": "期货品种",
                "row_count": variety_count,
                "quality_status": "good" if variety_count else "bad",
            },
            {
                "dataset_name": "kline_data",
                "label": "K 线数据",
                **kline_coverage,
                "quality_status": "good" if kline_coverage["row_count"] else "warning",
            },
            {
                "dataset_name": "realtime_quotes",
                "label": "实时行情",
                **realtime_coverage,
                "quality_status": "good" if realtime_count else "warning",
            },
        ]
        recommendations = ["优先使用 kline_data 做回测和技术分析，使用 realtime_quotes 做当前行情快照。"]
        if issues:
            recommendations.append("存在 warning/bad 数据集时，建议先补齐采集或回填任务。")

        return DataQualityReport(
            scope={"dataset": "all", "checked_at": datetime.now(UTC).isoformat()},
            status=status,
            score=score,
            coverage={
                "dataset_count": len(datasets),
                "variety_count": variety_count,
                "kline_row_count": kline_coverage["row_count"],
                "realtime_row_count": realtime_count,
            },
            issues=issues,
            recommendations=recommendations,
            datasets=datasets,
        )

    def check_realtime(self, symbol: str | None = None) -> DataQualityReport:
        """检查实时行情数据是否可用。"""
        issues: list[DataQualityIssue] = []
        coverage = get_realtime_coverage(self.db, symbol=symbol)

        query = self.db.query(RealtimeQuoteDB).join(VarietyDB, RealtimeQuoteDB.variety_id == VarietyDB.id)
        if symbol:
            query = query.filter(VarietyDB.symbol == symbol.upper())
        invalid = (
            query.filter(
                (RealtimeQuoteDB.current_price <= 0)
                | (RealtimeQuoteDB.volume < 0)
                | (RealtimeQuoteDB.high < RealtimeQuoteDB.low)
            )
            .limit(5)
            .all()
        )

        if coverage["row_count"] == 0:
            issues.append(DataQualityIssue("bad", "REALTIME_NO_DATA", "未找到匹配的实时行情数据"))
        if invalid:
            issues.append(
                DataQualityIssue(
                    "bad",
                    "REALTIME_INVALID_QUOTE",
                    "发现实时行情价格或成交量异常",
                    sample=[{"id": row.id, "current_price": float(row.current_price)} for row in invalid],
                )
            )

        status, score = score_issues(issues)
        return DataQualityReport(
            scope={"dataset": "realtime_quotes", "symbol": symbol},
            status=status,
            score=score,
            coverage=coverage,
            issues=issues,
            recommendations=_recommendations(status, "实时行情"),
        )

    def check_kline(self, symbol: str, period: str = "1d") -> DataQualityReport:
        """检查指定品种和周期的 K 线数据质量。"""
        symbol = symbol.upper()
        variety = self.db.query(VarietyDB).filter(VarietyDB.symbol == symbol).first()
        scope = {"dataset": "kline_data", "symbol": symbol, "period": period}
        if variety is None:
            issue = DataQualityIssue("bad", "VARIETY_NOT_FOUND", f"未找到品种 {symbol}")
            return DataQualityReport(
                scope=scope,
                status="bad",
                score=0,
                coverage={"row_count": 0},
                issues=[issue],
                recommendations=["请先确认品种代码或初始化 varieties 表。"],
            )

        coverage = get_kline_coverage(self.db, variety.id, period)
        issues: list[DataQualityIssue] = []
        if coverage["row_count"] == 0:
            issues.append(DataQualityIssue("bad", "KLINE_NO_DATA", f"{symbol} 缺少 {period} K 线数据"))
        else:
            for issue in (
                check_kline_ohlc(self.db, variety.id, period),
                check_kline_duplicates(self.db, variety.id, period),
            ):
                if issue is not None:
                    issues.append(issue)
            trading_dates = [
                row[0]
                for row in (
                    self.db.query(KlineDataDB.trading_date)
                    .filter(
                        KlineDataDB.variety_id == variety.id,
                        KlineDataDB.period == period,
                        KlineDataDB.trading_date.isnot(None),
                    )
                    .distinct()
                    .order_by(KlineDataDB.trading_date.asc())
                    .all()
                )
            ]
            if period == "1d":
                gap_issue = check_daily_date_gaps(trading_dates)
                if gap_issue is not None:
                    issues.append(gap_issue)

        status, score = score_issues(issues)
        coverage["missing_dates"] = next(
            (len(issue.sample) for issue in issues if issue.code == "KLINE_MISSING_DATES"),
            0,
        )
        return DataQualityReport(
            scope=scope,
            status=status,
            score=score,
            coverage=coverage,
            issues=issues,
            recommendations=_recommendations(status, f"{symbol} {period} K 线"),
        )

    def _dataset_summary(self, dataset_name: str) -> dict[str, Any]:
        if dataset_name == "kline_data":
            row = self.db.query(KlineDataDB).count()
            coverage_row = (
                self.db.query(KlineDataDB.trading_date)
                .filter(KlineDataDB.trading_date.isnot(None))
                .order_by(KlineDataDB.trading_date.asc())
                .first()
            )
            latest_row = (
                self.db.query(KlineDataDB.trading_date)
                .filter(KlineDataDB.trading_date.isnot(None))
                .order_by(KlineDataDB.trading_date.desc())
                .first()
            )
            return {
                "row_count": row,
                "first_date": coverage_row[0].isoformat() if coverage_row else None,
                "last_date": latest_row[0].isoformat() if latest_row else None,
            }
        return {"row_count": 0}


def _resolve_period(query: str) -> str:
    text = query.upper()
    explicit = re.search(r"\b(1D|DAY|D|1H|60M|30M|15M|5M|1M)\b", text)
    if explicit:
        value = explicit.group(1)
        return {"DAY": "1d", "D": "1d"}.get(value, value.lower())
    if "日" in query:
        return "1d"
    return "1d"


def _looks_like_inventory_query(query: str) -> bool:
    return any(keyword in query for keyword in ("有哪些数据", "数据资产", "库里", "盘点", "数据目录", "可用数据"))


def _looks_like_realtime_query(query: str) -> bool:
    return any(keyword in query for keyword in ("实时", "最新", "行情"))


def _looks_like_kline_query(query: str) -> bool:
    return any(keyword in query for keyword in ("K", "k", "日线", "日 K", "K线", "k线", "回测"))


def _recommendations(status: str, target: str) -> list[str]:
    if status == "good":
        return [f"{target} 数据质量良好，可用于分析、回测或 Agent 上下文。"]
    if status == "warning":
        return [f"{target} 可谨慎使用；建议先核对 warning 项，重要回测前补齐缺口。"]
    return [f"{target} 当前不建议直接用于回测或因子评估，请先修复 bad 级别数据问题。"]
