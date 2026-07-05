"""交易员 Agent。

模拟经验丰富的期货交易员，基于多周期图表研判，输出具体交易计划与风控方案。

支持交易风格：
- scalping: 日内剥头皮（数分钟 ~ 数小时）
- intraday_swing: 日内波段（1 小时 ~ 当日收盘）
- short_term_trend: 中短趋势（数天 ~ 2 周）
- medium_term_trend: 中期趋势（2 周 ~ 1 个月）
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator
from typing import Any

import pandas as pd

from services.agent.core import Agent, AgentResult, AgentStatus
from services.agent.data_tools import _get_kline_data, _get_realtime_quote, _get_variety_info
from services.agent.trader.candlestick import calculate_bull_bear_strength, detect_candlestick_patterns
from services.agent.trader.market_structure import find_support_resistance
from services.agent.trader.multi_timeframe import analyze_multi_timeframe
from services.agent.trader.risk_check import validate_trade_plan
from services.agent.trader.trade_plan import TradingStyle, generate_trade_plan
from services.agent.utils import resolve_symbol

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是「期货交流社区」的交易员 Agent。\n"
    "你是一位经验丰富的期货交易员，擅长日内波段、日内剥头皮、中短趋势交易。\n"
    "你能够读懂 K 线背后的多空力量变化，通过多周期图表识别趋势，并给出具体的交易计划。\n"
    "\n"
    "规则：\n"
    "1. 分析基于真实 K 线数据，结果客观、可复现\n"
    "2. 必须给出明确的方向、入场、止损、止盈、仓位建议\n"
    "3. 严格执行风控：单笔风险默认不超过账户 2%，盈亏比不足时观望\n"
    "4. 所有输出仅供参考，不构成投资建议\n"
)

_DEFAULT_ACCOUNT_BALANCE = 100000.0
_DEFAULT_RISK_PER_TRADE = 0.02

_TRADING_STYLE_KEYWORDS: dict[TradingStyle, list[str]] = {
    "scalping": ["剥头皮", "scalp", "超短线", "短线刷单"],
    "intraday_swing": ["日内波段", "日内", "day trade", "日内交易"],
    "short_term_trend": ["中短趋势", "短线趋势", "几天", "数日", "一周"],
    "medium_term_trend": ["中期趋势", "趋势", "两周", "一个月", "中长线"],
}

_TIMEFRAME_PREFERENCE: dict[str, list[str]] = {
    "scalping": ["5m", "15m", "1h"],
    "intraday_swing": ["15m", "1h", "4h"],
    "short_term_trend": ["1h", "4h", "1d"],
    "medium_term_trend": ["4h", "1d"],
}


def _extract_trading_style(query: str) -> TradingStyle | None:
    """从用户查询中提取交易风格。"""
    query_lower = query.lower()
    for style, keywords in _TRADING_STYLE_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in query_lower:
                return style
    return None


def _extract_timeframe_preference(query: str) -> list[str] | None:
    """从用户查询中提取周期偏好。"""
    # 匹配类似 "15分钟"、"1小时"、"日线" 等
    mapping = {
        "日线": "1d",
        "日线级别": "1d",
        "4小时": "4h",
        "4h": "4h",
        "1小时": "1h",
        "小时线": "1h",
        "1h": "1h",
        "15分钟": "15m",
        "15分": "15m",
        "15m": "15m",
        "5分钟": "5m",
        "5分": "5m",
        "5m": "5m",
    }
    found = []
    # 按长度降序，避免 "15分钟" 被 "分钟" 覆盖
    for kw, tf in sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True):
        if kw in query:
            found.append(tf)
    return found if found else None


def _extract_account_balance(query: str) -> float | None:
    """从查询中提取账户资金。"""
    # 匹配 "账户 10 万"、"资金 100000"、"10万" 等
    patterns = [
        r"(?:账户|资金|本金)\s*(\d+\.?\d*)\s*万",
        r"(\d+\.?\d*)\s*万\s*(?:账户|资金|本金)",
        r"(?:账户|资金|本金)\s*(\d{5,})\s*(?:元)?",
    ]
    for pattern in patterns:
        match = re.search(pattern, query)
        if match:
            value = float(match.group(1))
            if value < 1000:
                value *= 10000
            return value
    return None


def _extract_risk_per_trade(query: str) -> float | None:
    """从查询中提取单笔风险比例。"""
    match = re.search(r"(?:单笔风险|风险比例|每笔风险)\s*(\d+\.?\d*)\s*%", query)
    if match:
        return float(match.group(1)) / 100
    return None


class TraderAgent(Agent):
    """交易员 Agent。

    输入：品种代码 + 交易风格（可选）+ 周期偏好（可选）+ 账户资金（可选）
    输出：多周期趋势研判 + 具体交易计划 + 风控校验
    """

    name = "trader"
    description = "期货交易员专家，基于多周期图表研判输出具体交易计划与风控方案"

    async def run(self, query: str) -> AgentResult:
        """执行交易员研判任务。"""
        self._add_step("thought", f"开始交易研判：{query}")

        db = self.context.db

        # 1. 解析参数
        symbol = resolve_symbol(db, query)
        if not symbol:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message="无法从查询中识别品种代码，请提供品种代码（如 RB、AU）或品种名称",
                steps=self.get_steps(),
            )

        style = _extract_trading_style(query) or "intraday_swing"
        custom_timeframes = _extract_timeframe_preference(query)
        account_balance = _extract_account_balance(query) or _DEFAULT_ACCOUNT_BALANCE
        risk_per_trade = _extract_risk_per_trade(query) or _DEFAULT_RISK_PER_TRADE

        self._add_step(
            "action",
            f"解析参数：品种={symbol}，风格={style}，资金={account_balance:.0f}，单笔风险={risk_per_trade * 100:.1f}%",
        )

        # 2. 获取品种信息
        self._emit_progress("正在获取品种信息...")
        variety_info = _get_variety_info(db, symbol)
        if not variety_info:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=f"未找到品种 {symbol}",
                steps=self.get_steps(),
            )
        self._add_step("observation", f"品种信息：{variety_info['name']} ({variety_info['exchange']})")

        # 3. 获取实时行情
        self._emit_progress("正在获取实时行情...")
        quote = _get_realtime_quote(db, symbol)
        current_price = quote.get("current_price") if quote else None
        if current_price is None:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=f"无法获取品种 {symbol} 的当前价格",
                steps=self.get_steps(),
            )
        current_price = float(current_price)
        self._add_step("observation", f"实时行情：{quote}")

        # 4. 确定分析周期
        timeframes = custom_timeframes or _TIMEFRAME_PREFERENCE.get(style, ["15m", "1h", "4h"])

        # 确保包含日线作为大周期参考
        if "1d" not in timeframes:
            timeframes.append("1d")

        # 去重并保持顺序
        seen = set()
        ordered_timeframes = []
        for tf in timeframes:
            if tf not in seen:
                seen.add(tf)
                ordered_timeframes.append(tf)
        timeframes = ordered_timeframes

        self._add_step("action", f"分析周期：{', '.join(timeframes)}")

        # 5. 拉取多周期 K 线
        self._emit_progress("正在拉取多周期 K 线数据...")
        timeframe_data: dict[str, pd.DataFrame] = {}
        kline_summary: list[dict[str, Any]] = []

        for tf in timeframes:
            # 不同周期需要不同数据量
            limit_map = {"1d": 120, "4h": 120, "1h": 120, "15m": 120, "5m": 120}
            kline = _get_kline_data(db, symbol, period=tf, limit=limit_map.get(tf, 100))
            if not kline or len(kline) < 20:
                self._add_step("system", f"周期 {tf} 数据不足，跳过")
                continue

            df = pd.DataFrame(kline)
            df["time"] = pd.to_datetime(df["time"])
            df = df.sort_values("time").reset_index(drop=True)
            timeframe_data[tf] = df
            kline_summary.append({"timeframe": tf, "bars": len(kline)})

        if not timeframe_data:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=f"品种 {symbol} 各周期 K 线数据均不足，无法研判",
                steps=self.get_steps(),
            )

        self._add_step("observation", f"多周期 K 线数据：{kline_summary}")

        # 6. 多周期趋势研判
        self._emit_progress("正在进行多周期趋势研判...")
        multi_tf = analyze_multi_timeframe(timeframe_data)
        self._add_step(
            "system",
            f"多周期研判：{multi_tf['summary']}，共振度 {multi_tf['alignment_score']:.0f}%",
        )

        # 7. 入场周期 K 线形态与多空力量
        entry_tf = multi_tf["entry_timeframe"] or list(timeframe_data.keys())[-1]
        entry_df = timeframe_data.get(entry_tf)
        candlestick_patterns = []
        bull_bear_strength = {"score": 0.0, "description": "数据不足"}
        if entry_df is not None and len(entry_df) >= 5:
            candlestick_patterns = detect_candlestick_patterns(entry_df)
            bull_bear_strength = calculate_bull_bear_strength(entry_df)
            self._add_step(
                "system",
                f"{entry_tf} K线形态：识别到 {len(candlestick_patterns)} 个形态，多空力量 {bull_bear_strength['description']}",
            )

        # 8. 支撑阻力位
        key_levels = find_support_resistance(entry_df, lookback=20) if entry_df is not None else []
        self._add_step(
            "system",
            f"关键位：{len(key_levels)} 个（支撑/阻力）",
        )

        # 9. 生成交易计划
        self._emit_progress("正在生成交易计划...")
        multiplier = variety_info.get("multiplier") or 1.0
        trade_plan = generate_trade_plan(
            symbol=symbol,
            current_price=current_price,
            dominant_trend=multi_tf["dominant_trend"],
            direction=multi_tf["direction"],
            entry_timeframe=entry_tf,
            timeframe_data=timeframe_data,
            style=style,
            account_balance=account_balance,
            risk_per_trade=risk_per_trade,
            multiplier=float(multiplier),
        )

        if trade_plan:
            self._add_step(
                "system",
                f"交易计划：{trade_plan['direction']}，入场 {trade_plan['entry_price']}，止损 {trade_plan['stop_loss']}，止盈 {trade_plan['take_profit']}，仓位 {trade_plan['position_size']} 手，R:R={trade_plan['risk_reward_ratio']}",
            )
        else:
            self._add_step("system", "当前条件不满足交易计划要求，建议观望")

        # 10. 风控校验
        self._emit_progress("正在进行风控校验...")
        risk_validation = validate_trade_plan(trade_plan, account_balance)
        self._add_step(
            "system",
            f"风控校验：{'通过' if risk_validation['valid'] else '未通过'}，风险占比 {risk_validation['risk_percent'] * 100:.2f}%",
        )

        # 11. 构建输出报告
        report = self._build_report(
            symbol=symbol,
            variety_info=variety_info,
            current_price=current_price,
            quote=quote,
            multi_tf=multi_tf,
            entry_tf=entry_tf,
            candlestick_patterns=candlestick_patterns,
            bull_bear_strength=bull_bear_strength,
            key_levels=key_levels,
            trade_plan=trade_plan,
            risk_validation=risk_validation,
            style=style,
            account_balance=account_balance,
            risk_per_trade=risk_per_trade,
        )

        # 12. 最终答案文本
        answer = self._build_answer(report)

        self._add_step("result", answer)

        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=answer,
            data=report,
            steps=self.get_steps(),
            task_id=self.context.task_id,
        )

    async def run_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """真实 SSE 流式执行。"""
        async for event in self._stream_run(query):
            yield event

    def _build_report(
        self,
        symbol: str,
        variety_info: dict[str, Any],
        current_price: float,
        quote: dict[str, Any] | None,
        multi_tf: dict[str, Any],
        entry_tf: str,
        candlestick_patterns: list[dict[str, Any]],
        bull_bear_strength: dict[str, Any],
        key_levels: list[dict[str, Any]],
        trade_plan: dict[str, Any] | None,
        risk_validation: dict[str, Any],
        style: TradingStyle,
        account_balance: float,
        risk_per_trade: float,
    ) -> dict[str, Any]:
        """构建结构化报告。"""
        return {
            "symbol": symbol,
            "name": variety_info.get("name"),
            "exchange": variety_info.get("exchange"),
            "current_price": current_price,
            "change_percent": quote.get("change_percent") if quote else None,
            "style": style,
            "account_balance": account_balance,
            "risk_per_trade": risk_per_trade,
            "dominant_trend": multi_tf["dominant_trend"],
            "direction": multi_tf["direction"],
            "alignment_score": multi_tf["alignment_score"],
            "entry_timeframe": entry_tf,
            "timeframe_analysis": multi_tf["timeframe_analysis"],
            "conflict_notes": multi_tf["conflict_notes"],
            "candlestick_patterns": candlestick_patterns[-5:] if candlestick_patterns else [],
            "bull_bear_strength": bull_bear_strength,
            "key_levels": key_levels,
            "trade_plan": trade_plan,
            "risk_validation": risk_validation,
            "disclaimer": "以上分析仅供参考，不构成投资建议。期货交易风险极高，请根据自身情况独立判断。",
        }

    def _build_answer(self, report: dict[str, Any]) -> str:
        """构建面向用户的最终答案文本。"""
        lines: list[str] = []

        symbol = report["symbol"]
        name = report.get("name", symbol)
        current_price = report["current_price"]
        change = report.get("change_percent")
        change_text = f"（{change:+.2f}%）" if change is not None else ""

        lines.append(f"## {name}（{symbol}）交易研判")
        lines.append(f"当前价格：{current_price:.2f}{change_text}")
        lines.append("")

        # 趋势研判
        trend_map = {
            "uptrend": "上涨趋势",
            "downtrend": "下跌趋势",
            "sideways": "横盘整理",
            "range_bound": "区间震荡",
        }
        trend_text = trend_map.get(report["dominant_trend"], "方向不明")
        lines.append(f"**主要趋势**：{trend_text}")
        lines.append(f"**周期共振度**：{report['alignment_score']:.0f}%")
        lines.append(f"**推荐入场周期**：{report['entry_timeframe']}")
        if report.get("conflict_notes"):
            lines.append(f"**周期矛盾**：{report['conflict_notes']}")
        lines.append("")

        # K线形态
        patterns = report.get("candlestick_patterns", [])
        if patterns:
            recent_patterns = [p for p in patterns if p.get("recent")]
            if recent_patterns:
                pattern_desc = "、".join(p["description"] for p in recent_patterns)
                lines.append(f"**K线形态**：{pattern_desc}")
        strength = report.get("bull_bear_strength", {})
        lines.append(f"**多空力量**：{strength.get('description', '未知')}（评分 {strength.get('score', 0):.2f}）")
        lines.append("")

        # 交易计划
        trade_plan = report.get("trade_plan")
        if trade_plan and report["risk_validation"].get("valid"):
            direction_map = {"long": "做多", "short": "做空"}
            lines.append(f"### 交易计划（{direction_map.get(trade_plan['direction'], trade_plan['direction'])}）")
            lines.append(f"- 交易风格：{self._style_text(trade_plan['style'])}")
            lines.append(f"- 入场条件：{trade_plan['entry_condition']}")
            lines.append(f"- 入场参考价：{trade_plan['entry_price']:.2f}")
            lines.append(f"- 止损价：{trade_plan['stop_loss']:.2f}")
            lines.append(f"- 止盈价：{trade_plan['take_profit']:.2f}")
            lines.append(f"- 建议仓位：{trade_plan['position_size']} 手")
            lines.append(
                f"- 单笔风险：{trade_plan['actual_risk_amount']:.0f} 元（账户 {report['risk_per_trade'] * 100:.1f}%）"
            )
            lines.append(f"- 盈亏比：1:{trade_plan['risk_reward_ratio']:.2f}")
            lines.append(f"- 预计持有周期：{trade_plan['holding_period']}")
            lines.append(f"- 计划失效条件：{trade_plan['invalidation']}")
            lines.append(f"- 研判置信度：{self._confidence_text(trade_plan['confidence'])}")
        else:
            lines.append("### 交易计划")
            if trade_plan and not report["risk_validation"].get("valid"):
                lines.append("当前交易计划未通过风控校验，建议观望。")
                for warning in report["risk_validation"].get("warnings", []):
                    lines.append(f"- ⚠️ {warning}")
            else:
                lines.append("当前条件不满足交易要求，建议观望。")

        lines.append("")

        # 风控提示
        lines.append("### 风控提示")
        for rec in report["risk_validation"].get("recommendations", []):
            lines.append(f"- {rec}")
        lines.append("")

        # 免责声明
        lines.append(f"> {report['disclaimer']}")

        return "\n".join(lines)

    def _style_text(self, style: TradingStyle) -> str:
        """交易风格中文文本。"""
        mapping = {
            "scalping": "日内剥头皮",
            "intraday_swing": "日内波段",
            "short_term_trend": "中短趋势",
            "medium_term_trend": "中期趋势",
        }
        return mapping.get(style, style)

    def _confidence_text(self, confidence: str) -> str:
        """置信度中文文本。"""
        mapping = {"high": "高", "medium": "中", "low": "低"}
        return mapping.get(confidence, confidence)
