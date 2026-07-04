"""策略编译 Agent。

将用户自然语言策略描述转换为结构化的策略 DSL（JSON）。
支持均线交叉、MACD、RSI、布林带等多种策略模板。

核心原则：
1. 确定性解析优先：规则匹配 + 正则提取
2. LLM 增强：当规则无法覆盖时，使用 LLM 补充解析
3. 严格校验：表达式白名单 + 字段合法性检查
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, AsyncIterator

from services.agent.context import AgentContext
from services.agent.core import Agent, AgentEvent, AgentEventType, AgentResult, AgentStatus
from services.agent.utils import resolve_symbol, resolve_symbols

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 表达式白名单
# ------------------------------------------------------------------

_VALID_INDICATORS = frozenset({
    "sma", "ema", "rsi", "macd", "macd_dif", "macd_dea", "macd_bar",
    "boll_upper", "boll_mid", "boll_lower", "kdj_k", "kdj_d", "kdj_j",
    "atr", "cci", "obv", "adx", "dmi_plus", "dmi_minus", "wr", "volume",
    "close", "open", "high", "low", "pre_close", "change_percent",
})

_VALID_OPERATORS = frozenset({
    "cross_above", "cross_below", "above", "below",
    "greater_than", "less_than", "equal", "between",
    "increase_by", "decrease_by",
})

_VALID_PERIODS = frozenset({"1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"})

_VALID_DIRECTIONS = frozenset({"long", "short"})

_VALID_RISK_TYPES = frozenset({
    "fixed_lots", "fixed_cash", "risk_percent", "atr_multiple",
    "fixed_price", "percent_below", "percent_above",
    "risk_reward_ratio", "trailing_stop", "target_price",
})


# ------------------------------------------------------------------
# Strategy DSL
# ------------------------------------------------------------------

class StrategyDSL:
    """策略 DSL 结构。"""

    def __init__(
        self,
        name: str,
        description: str,
        universe: list[str],
        timeframe: str,
        direction: str,
        entry: dict[str, Any],
        exit: dict[str, Any],
        risk: dict[str, Any],
    ):
        self.name = name
        self.description = description
        self.universe = universe
        self.timeframe = timeframe
        self.direction = direction
        self.entry = entry
        self.exit = exit
        self.risk = risk

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "universe": self.universe,
            "timeframe": self.timeframe,
            "direction": self.direction,
            "entry": self.entry,
            "exit": self.exit,
            "risk": self.risk,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ------------------------------------------------------------------
# 策略解析器
# ------------------------------------------------------------------

class StrategyParser:
    """基于规则的自然语言策略解析器。"""

    # 策略模板：关键词 -> 解析函数
    # 注意：顺序重要 —— 更具体/更通用的关键词在前，避免「RSI」吃掉带「且」的均线+RSI复合查询
    _TEMPLATES = [
        ("均线交叉", "_parse_ma_cross"),
        ("均线", "_parse_ma_cross"),
        ("MACD", "_parse_macd"),
        ("布林带", "_parse_bollinger"),
        ("突破", "_parse_breakout"),
        ("RSI", "_parse_rsi"),
    ]

    def __init__(self, db) -> None:
        self.db = db

    def parse(self, query: str) -> StrategyDSL | None:
        """解析自然语言策略描述。"""
        # 1. 提取品种（支持多品种）
        symbols = resolve_symbols(self.db, query)
        if not symbols:
            return None

        # 2. 提取周期
        timeframe = _extract_timeframe(query)

        # 3. 提取方向
        direction = "short" if any(w in query for w in ("做空", "空头", "卖空", "short")) else "long"

        # 4. 检测逻辑连接词（AND / OR）
        logic = _detect_logic(query)

        # 5. 匹配策略模板
        for keyword, method_name in self._TEMPLATES:
            if keyword in query:
                method = getattr(self, method_name)
                return method(query, symbols, timeframe, direction, logic)

        # 6. 默认模板：均线交叉
        return self._parse_ma_cross(query, symbols, timeframe, direction, logic)

    def _parse_ma_cross(self, query: str, symbols: list[str], timeframe: str, direction: str, logic: str) -> StrategyDSL:
        """解析均线交叉策略。"""
        # 提取均线周期
        ma_matches = re.findall(r"(\d+)\s*(?:日|天|周期|根)?(?:均线|ma|MA)", query)
        if len(ma_matches) >= 2:
            short_window = int(ma_matches[0])
            long_window = int(ma_matches[1])
        else:
            # 默认 5 日上穿 20 日
            short_window = 5
            long_window = 20

        short_indicator = f"sma{short_window}"
        long_indicator = f"sma{long_window}"

        entry_op = "cross_above" if direction == "long" else "cross_below"
        exit_op = "cross_below" if direction == "long" else "cross_above"

        base_conditions = [
            {"indicator": short_indicator, "operator": entry_op, "indicator2": long_indicator}
        ]
        extra_conditions = _parse_extra_conditions(query)

        return StrategyDSL(
            name=f"{symbols[0] if len(symbols) == 1 else '多品种'} 均线交叉策略 ({short_window}/{long_window})",
            description=f"{direction}方向：{short_indicator} {entry_op} {long_indicator} 入场，反向交叉出场",
            universe=symbols,
            timeframe=timeframe,
            direction=direction,
            entry={
                "conditions": base_conditions + extra_conditions,
                "logic": logic,
            },
            exit={
                "conditions": [
                    {"indicator": short_indicator, "operator": exit_op, "indicator2": long_indicator}
                ],
                "logic": "and",
            },
            risk=_default_risk(query),
        )

    def _parse_macd(self, query: str, symbols: list[str], timeframe: str, direction: str, logic: str) -> StrategyDSL:
        """解析 MACD 策略。"""
        entry_conditions = []
        exit_conditions = []

        if "金叉" in query or "dif上穿dea" in query:
            entry_conditions.append({"indicator": "macd_dif", "operator": "cross_above", "indicator2": "macd_dea"})
        elif "dif大于dea" in query or "dif在dea上方" in query:
            entry_conditions.append({"indicator": "macd_dif", "operator": "above", "indicator2": "macd_dea"})
        else:
            entry_conditions.append({"indicator": "macd_dif", "operator": "cross_above", "indicator2": "macd_dea"})

        if "死叉" in query or "dif下穿dea" in query:
            exit_conditions.append({"indicator": "macd_dif", "operator": "cross_below", "indicator2": "macd_dea"})
        else:
            exit_conditions.append({"indicator": "macd_dif", "operator": "cross_below", "indicator2": "macd_dea"})

        # Multi-condition: parse additional conditions from the query
        extra_entry = _parse_extra_conditions(query)
        extra_exit = _parse_extra_exit_conditions(query)

        return StrategyDSL(
            name=f"{symbols[0] if len(symbols) == 1 else '多品种'} MACD 策略",
            description="基于 MACD 金叉/死叉信号",
            universe=symbols,
            timeframe=timeframe,
            direction=direction,
            entry={"conditions": entry_conditions + extra_entry, "logic": logic},
            exit={"conditions": exit_conditions + extra_exit, "logic": "and"},
            risk=_default_risk(query),
        )

    def _parse_rsi(self, query: str, symbols: list[str], timeframe: str, direction: str, logic: str) -> StrategyDSL:
        """解析 RSI 策略。"""
        # 提取 RSI 阈值
        threshold_match = re.search(r"RSI\s*(?:低于|小于|低于|below|<)?\s*(\d+)", query, re.IGNORECASE)
        threshold = int(threshold_match.group(1)) if threshold_match else 30

        if direction == "long":
            entry_conditions = [{"indicator": "rsi24", "operator": "less_than", "value": threshold}]
            exit_conditions = [{"indicator": "rsi24", "operator": "greater_than", "value": 70}]
        else:
            entry_conditions = [{"indicator": "rsi24", "operator": "greater_than", "value": 70}]
            exit_conditions = [{"indicator": "rsi24", "operator": "less_than", "value": threshold}]

        extra_entry = _parse_extra_conditions(query)

        return StrategyDSL(
            name=f"{symbols[0] if len(symbols) == 1 else '多品种'} RSI 反转策略",
            description=f"RSI 超{'卖' if direction == 'long' else '买'}入场（阈值 {threshold}）",
            universe=symbols,
            timeframe=timeframe,
            direction=direction,
            entry={"conditions": entry_conditions + extra_entry, "logic": logic},
            exit={"conditions": exit_conditions, "logic": "and"},
            risk=_default_risk(query),
        )

    def _parse_bollinger(self, query: str, symbols: list[str], timeframe: str, direction: str, logic: str) -> StrategyDSL:
        """解析布林带策略。"""
        if direction == "long":
            entry_conditions = [{"indicator": "close", "operator": "cross_above", "indicator2": "boll_lower"}]
            exit_conditions = [{"indicator": "close", "operator": "cross_below", "indicator2": "boll_mid"}]
        else:
            entry_conditions = [{"indicator": "close", "operator": "cross_below", "indicator2": "boll_upper"}]
            exit_conditions = [{"indicator": "close", "operator": "cross_above", "indicator2": "boll_mid"}]

        extra_entry = _parse_extra_conditions(query)

        return StrategyDSL(
            name=f"{symbols[0] if len(symbols) == 1 else '多品种'} 布林带策略",
            description="基于布林带上下轨的均值回归策略",
            universe=symbols,
            timeframe=timeframe,
            direction=direction,
            entry={"conditions": entry_conditions + extra_entry, "logic": logic},
            exit={"conditions": exit_conditions, "logic": "and"},
            risk=_default_risk(query),
        )

    def _parse_breakout(self, query: str, symbols: list[str], timeframe: str, direction: str, logic: str) -> StrategyDSL:
        """解析突破策略。"""
        # 提取周期（如 20 日高点）
        window_match = re.search(r"(\d+)\s*(?:日|天|周期|根)", query)
        window = int(window_match.group(1)) if window_match else 20

        if direction == "long":
            entry_conditions = [{"indicator": "close", "operator": "cross_above", "indicator2": f"high_{window}"}]
        else:
            entry_conditions = [{"indicator": "close", "operator": "cross_below", "indicator2": f"low_{window}"}]

        extra_entry = _parse_extra_conditions(query)

        return StrategyDSL(
            name=f"{symbols[0] if len(symbols) == 1 else '多品种'} {window}日突破策略",
            description=f"突破最近 {window} 周期高低点",
            universe=symbols,
            timeframe=timeframe,
            direction=direction,
            entry={"conditions": entry_conditions + extra_entry, "logic": logic},
            exit={"conditions": [], "logic": "and"},  # 需结合止损
            risk=_default_risk(query),
        )


# ------------------------------------------------------------------
# 校验器
# ------------------------------------------------------------------

class StrategyValidator:
    """策略 DSL 校验器。"""

    @classmethod
    def validate(cls, dsl: StrategyDSL) -> list[str]:
        """校验策略 DSL，返回错误列表（空列表表示通过）。"""
        errors = []

        # 1. 基础字段
        if not dsl.universe:
            errors.append("universe 不能为空")
        if dsl.timeframe not in _VALID_PERIODS:
            errors.append(f"不支持的周期：{dsl.timeframe}")
        if dsl.direction not in _VALID_DIRECTIONS:
            errors.append(f"不支持的方向：{dsl.direction}")

        # 2. 入场条件
        errors.extend(cls._validate_conditions(dsl.entry.get("conditions", []), "entry"))

        # 3. 出场条件
        errors.extend(cls._validate_conditions(dsl.exit.get("conditions", []), "exit"))

        # 4. 风控参数
        errors.extend(cls._validate_risk(dsl.risk))

        return errors

    @classmethod
    def _validate_conditions(cls, conditions: list[dict], context: str) -> list[str]:
        errors = []
        for i, cond in enumerate(conditions):
            prefix = f"{context}.conditions[{i}]"
            indicator = cond.get("indicator")
            operator = cond.get("operator")
            indicator2 = cond.get("indicator2")
            value = cond.get("value")

            if not indicator:
                errors.append(f"{prefix} 缺少 indicator")
            elif not _is_valid_indicator(indicator):
                errors.append(f"{prefix} 不支持的指标：{indicator}")

            if not operator:
                errors.append(f"{prefix} 缺少 operator")
            elif operator not in _VALID_OPERATORS:
                errors.append(f"{prefix} 不支持的操作符：{operator}")

            # cross 操作符需要 indicator2
            if operator in ("cross_above", "cross_below") and not indicator2:
                errors.append(f"{prefix} {operator} 需要 indicator2")
            if indicator2 and not _is_valid_indicator(indicator2):
                errors.append(f"{prefix} 不支持的指标2：{indicator2}")

            # 数值操作符需要 value
            if operator in ("greater_than", "less_than", "equal", "between") and value is None:
                errors.append(f"{prefix} {operator} 需要 value")

        return errors

    @classmethod
    def _validate_risk(cls, risk: dict) -> list[str]:
        errors = []
        position = risk.get("position_size", {})
        stop_loss = risk.get("stop_loss", {})
        take_profit = risk.get("take_profit", {})

        for name, config in [("position_size", position), ("stop_loss", stop_loss), ("take_profit", take_profit)]:
            if not config:
                continue
            risk_type = config.get("type")
            if risk_type and risk_type not in _VALID_RISK_TYPES:
                errors.append(f"risk.{name} 不支持的风险类型：{risk_type}")

        return errors


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------

def _is_valid_indicator(name: str) -> bool:
    """校验指标名是否合法，支持基础名及带周期/窗口后缀的变体（如 sma5、rsi24、high_20）。"""
    if name in _VALID_INDICATORS:
        return True
    # 提取基础名：去掉末尾 _?数字 后缀（sma5 -> sma, high_20 -> high）
    base = re.sub(r"[_-]?\d+$", "", name)
    return base in _VALID_INDICATORS


def _extract_timeframe(query: str) -> str:
    """从查询中提取周期。"""
    period_map = {
        "1分钟": "1m", "一分钟": "1m",
        "5分钟": "5m", "五分钟": "5m",
        "15分钟": "15m", "十五分钟": "15m",
        "30分钟": "30m", "三十分钟": "30m",
        "1小时": "1h", "一小时": "1h", "小时线": "1h",
        "4小时": "4h",
        "日线": "1d", "日K": "1d", "日k": "1d", "日": "1d",
        "周线": "1w", "周K": "1w", "周k": "1w", "周": "1w",
        "月线": "1mo", "月K": "1mo", "月k": "1mo", "月": "1mo",
    }
    for key, value in period_map.items():
        if key in query:
            return value
    return "1d"


def _default_risk(query: str) -> dict[str, Any]:
    """生成默认风控参数。"""
    # 提取止损：排除「跌破20日均线/周期/根」等技术指标表达
    stop_match = re.search(r"跌破\s*(\d+(?:\.\d+)?)(?!\d)(?!\s*(?:日|天|周期|根|ma|MA|均线))", query)
    stop_price = float(stop_match.group(1)) if stop_match else None

    # 提取止盈
    profit_match = re.search(r"(?:止盈|目标价)\s*(\d+(?:\.\d+)?)", query)
    profit_price = float(profit_match.group(1)) if profit_match else None

    # 提取仓位
    lots_match = re.search(r"(\d+)\s*手", query)
    lots = int(lots_match.group(1)) if lots_match else 1

    risk = {
        "position_size": {"type": "fixed_lots", "value": lots},
        "stop_loss": {"type": "atr_multiple", "value": 2.0},
        "take_profit": {"type": "risk_reward_ratio", "value": 2.0},
    }

    if stop_price:
        risk["stop_loss"] = {"type": "fixed_price", "value": stop_price}
    if profit_price:
        risk["take_profit"] = {"type": "target_price", "value": profit_price}

    return risk


# ------------------------------------------------------------------
# 多条件解析
# ------------------------------------------------------------------

_AND_CONNECTORS = re.compile(r"(且|并且|同时|and|AND|\s+\+\s+)")
_OR_CONNECTORS = re.compile(r"(或|或者|or|OR)")


def _detect_logic(query: str) -> str:
    """检测用户查询中的逻辑连接词，返回 'and' 或 'or'。"""
    if _OR_CONNECTORS.search(query):
        return "or"
    # 如果同时有多个条件但没有显式 OR，默认 AND
    return "and"


def _parse_extra_conditions(query: str) -> list[dict[str, Any]]:
    """从查询中解析额外入场条件（基于关键词）。"""
    conditions: list[dict[str, Any]] = []

    # 均线交叉 — 匹配 "(数字)(日/天)?上穿/下穿(数字)(日/天)?(均线/ma/MA)?"
    ma_crosses = re.findall(
        r"(\d+)\s*(?:日|天|周期|根)?\s*(?:均线|ma|MA)?\s*(?:上穿|下穿)\s*(\d+)\s*(?:日|天|周期|根)?\s*(?:均线|ma|MA)?",
        query,
    )
    # 如果找到额外的均线交叉条件，追加（主模板已处理第一组，跳过第一个匹配）
    first_primary_handled = False
    for short_match, long_match in ma_crosses:
        # Skip the first cross that the main template handles
        if not first_primary_handled:
            first_primary_handled = True
            continue
        short_w = int(short_match)
        long_w = int(long_match)
        entry_op = "cross_above" if "下穿" not in query else "cross_below"
        conditions.append({"indicator": f"sma{short_w}", "operator": entry_op, "indicator2": f"sma{long_w}"})

    # RSI 相关
    rsi_below = re.search(r"RSI\s*(?:低于|小于|below)\s*(\d+)", query, re.IGNORECASE)
    rsi_above = re.search(r"RSI\s*(?:高于|大于|above)\s*(\d+)", query, re.IGNORECASE)
    if rsi_below:
        conditions.append({"indicator": "rsi24", "operator": "less_than", "value": int(rsi_below.group(1))})
    elif rsi_above:
        conditions.append({"indicator": "rsi24", "operator": "greater_than", "value": int(rsi_above.group(1))})

    # 成交量放大
    if re.search(r"成交量\s*(?:放大|增加|扩张|放量)", query):
        vol_mult_match = re.search(r"(\d+(?:\.\d+)?)\s*倍", query)
        vol_mult = float(vol_mult_match.group(1)) if vol_mult_match else 1.5
        conditions.append({"indicator": "volume", "operator": "greater_than", "value": vol_mult})

    # 成交量缩小
    if re.search(r"成交量\s*(?:缩小|萎缩|缩量|减少)", query):
        conditions.append({"indicator": "volume", "operator": "less_than", "value": 0.5})

    # 价格在均线上方/下方
    ma_above = re.search(r"(?:价格|收盘价?)\s*(?:在|位于)?\s*(\d+)\s*(?:日|天)?(?:均线|ma|MA)\s*(?:上方|之上|以上)", query)
    ma_below = re.search(r"(?:价格|收盘价?)\s*(?:在|位于)?\s*(\d+)\s*(?:日|天)?(?:均线|ma|MA)\s*(?:下方|之下|以下)", query)
    if ma_above:
        period = int(ma_above.group(1))
        conditions.append({"indicator": "close", "operator": "above", "indicator2": f"sma{period}"})
    elif ma_below:
        period = int(ma_below.group(1))
        conditions.append({"indicator": "close", "operator": "below", "indicator2": f"sma{period}"})

    # MACD 柱状图为正/为负
    if re.search(r"MACD\s*(?:柱|bar)\s*(?:为正|为正值|>0|大于0)", query, re.IGNORECASE):
        conditions.append({"indicator": "macd_bar", "operator": "greater_than", "value": 0})

    # DIF 在 DEA 上方/下方
    if "DIF在DEA上方" in query or "dif在dea上方" in query.lower():
        conditions.append({"indicator": "macd_dif", "operator": "above", "indicator2": "macd_dea"})
    elif "DIF在DEA下方" in query or "dif在dea下方" in query.lower():
        conditions.append({"indicator": "macd_dif", "operator": "below", "indicator2": "macd_dea"})

    # ADX 强度
    adx_above = re.search(r"ADX\s*(?:高于|大于|above|>)\s*(\d+)", query, re.IGNORECASE)
    if adx_above:
        conditions.append({"indicator": "adx", "operator": "greater_than", "value": int(adx_above.group(1))})

    # 突破高低点
    breakout = re.search(r"突破\s*(\d+)\s*(?:日|天|周期|根)?(?:高|低)点", query)
    if breakout:
        window = int(breakout.group(1))
        if "低点" in breakout.group():
            conditions.append({"indicator": "close", "operator": "cross_below", "indicator2": f"low_{window}"})
        else:
            conditions.append({"indicator": "close", "operator": "cross_above", "indicator2": f"high_{window}"})

    return conditions


def _parse_extra_exit_conditions(query: str) -> list[dict[str, Any]]:
    """从查询中解析额外出场条件。"""
    conditions: list[dict[str, Any]] = []

    # RSI 超买/超卖出場
    rsi_exit = re.search(r"(?:出场|离场|退出).*?RSI\s*(?:高于|大于|above|>)\s*(\d+)", query, re.IGNORECASE)
    if not rsi_exit:
        rsi_exit = re.search(r"RSI\s*(?:高于|大于|above|>)\s*(\d+)\s*(?:出场|离场|退出)", query, re.IGNORECASE)
    if rsi_exit:
        conditions.append({"indicator": "rsi24", "operator": "greater_than", "value": int(rsi_exit.group(1))})

    # 跌破均線出场
    ma_exit = re.search(r"跌破\s*(\d+)\s*(?:日|天)?(?:均线|ma|MA)\s*(?:出场|离场|退出)?", query)
    if ma_exit:
        period = int(ma_exit.group(1))
        conditions.append({"indicator": "close", "operator": "cross_below", "indicator2": f"sma{period}"})

    return conditions


# ------------------------------------------------------------------
# StrategyCompilerAgent
# ------------------------------------------------------------------

class StrategyCompilerAgent(Agent):
    """策略编译 Agent。

    将用户自然语言策略描述转换为结构化的策略 DSL（JSON），
    支持均线交叉、MACD、RSI、布林带、突破等策略模板。
    """

    name = "strategy_compiler"
    description = "策略编译专家，将自然语言策略描述转换为结构化 DSL"

    async def run(self, query: str) -> AgentResult:
        """执行策略编译。"""
        self._add_step("thought", f"开始解析策略：{query}")

        db = self.context.db

        # 1. 解析策略
        parser = StrategyParser(db)
        dsl = parser.parse(query)

        if dsl is None:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message="无法识别策略品种，请提供品种代码（如 RB、AU）或品种名称",
                steps=self.get_steps(),
            )

        self._add_step(
            "action",
            "策略解析完成",
            tool_name="StrategyParser",
            tool_input={"query": query},
            tool_output=dsl.to_dict(),
        )

        # 2. 校验 DSL
        errors = StrategyValidator.validate(dsl)
        if errors:
            self._add_step("error", f"策略校验失败：{'; '.join(errors)}")
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=f"策略校验失败：{'; '.join(errors)}",
                steps=self.get_steps(),
            )

        self._add_step("system", "策略 DSL 校验通过")

        # 3. 生成可读解释
        explanation = _format_explanation(dsl)
        self._add_step("system", f"生成策略解释：{explanation[:50]}...")

        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=explanation,
            data={
                "dsl": dsl.to_dict(),
                "json": dsl.to_json(),
                "valid": True,
                "warnings": [],
            },
            steps=self.get_steps(),
        )

    async def run_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行策略编译任务。

        按「解析意图 → 提取策略要素 → 生成 DSL → 校验 → 返回」各阶段
        yield 事件，前端可实时展示执行过程。
        """
        result = await self.run(query)

        for step in result.steps:
            yield AgentEvent(
                event_type=self._map_role_to_event_type(step.role),
                step_number=step.step_number,
                role=step.role,
                content=step.content,
                tool_name=step.tool_name,
                tool_input=step.tool_input,
                tool_output=step.tool_output,
            ).to_dict()

        if result.success:
            yield AgentEvent(
                event_type=AgentEventType.RESULT,
                content=result.answer,
                result=result.to_dict(),
            ).to_dict()
        else:
            yield AgentEvent(
                event_type=AgentEventType.ERROR,
                content=result.error_message or "策略编译失败",
                error_message=result.error_message,
                result=result.to_dict(),
            ).to_dict()

    @staticmethod
    def _map_role_to_event_type(role: str) -> AgentEventType:
        """将步骤 role 映射到 SSE 事件类型。"""
        mapping = {
            "thought": AgentEventType.THOUGHT,
            "action": AgentEventType.ACTION,
            "observation": AgentEventType.OBSERVATION,
            "system": AgentEventType.THOUGHT,
            "error": AgentEventType.ERROR,
        }
        return mapping.get(role, AgentEventType.THOUGHT)


def _format_explanation(dsl: StrategyDSL) -> str:
    """生成策略的可读解释。"""
    lines = [
        f"## {dsl.name}",
        "",
        f"{dsl.description}",
        "",
        "### 策略参数",
        f"- **品种**：{', '.join(dsl.universe)}",
        f"- **周期**：{dsl.timeframe}",
        f"- **方向**：{'做多' if dsl.direction == 'long' else '做空'}",
        "",
        "### 入场条件",
    ]

    entry_logic = dsl.entry.get("logic", "and")
    entry_conditions = dsl.entry.get("conditions", [])
    if len(entry_conditions) > 1:
        logic_label = "AND（同时满足）" if entry_logic == "and" else "OR（满足任一）"
        lines.append(f"**组合逻辑**：{logic_label}")
    for cond in entry_conditions:
        op_desc = _operator_desc(cond.get("operator"), cond.get("indicator"), cond.get("indicator2"), cond.get("value"))
        lines.append(f"- {op_desc}")
    if not entry_conditions:
        lines.append("- 无明确入场条件（需手动设置）")

    lines.extend(["", "### 出场条件"])
    exit_logic = dsl.exit.get("logic", "and")
    exit_conditions = dsl.exit.get("conditions", [])
    if len(exit_conditions) > 1:
        logic_label = "AND（同时满足）" if exit_logic == "and" else "OR（满足任一）"
        lines.append(f"**组合逻辑**：{logic_label}")
    for cond in exit_conditions:
        op_desc = _operator_desc(cond.get("operator"), cond.get("indicator"), cond.get("indicator2"), cond.get("value"))
        lines.append(f"- {op_desc}")
    if not exit_conditions:
        lines.append("- 无明确出场条件（建议结合止损/止盈）")

    risk = dsl.risk
    lines.extend(["", "### 风控参数"])
    pos = risk.get("position_size", {})
    sl = risk.get("stop_loss", {})
    tp = risk.get("take_profit", {})
    lines.append(f"- **仓位**：{pos.get('type', '—')} {pos.get('value', '')}")
    lines.append(f"- **止损**：{sl.get('type', '—')} {sl.get('value', '')}")
    lines.append(f"- **止盈**：{tp.get('type', '—')} {tp.get('value', '')}")

    lines.extend(["", "> 策略 DSL 已生成，可直接用于回测或预警。所有分析仅供参考，不构成投资建议。"])

    return "\n".join(lines)


def _operator_desc(operator: str, indicator: str, indicator2: str | None, value: Any) -> str:
    """将操作符转换为可读描述。"""
    op_map = {
        "cross_above": f"{indicator} 上穿 {indicator2}",
        "cross_below": f"{indicator} 下穿 {indicator2}",
        "above": f"{indicator} 在 {indicator2} 上方",
        "below": f"{indicator} 在 {indicator2} 下方",
        "greater_than": f"{indicator} > {value}",
        "less_than": f"{indicator} < {value}",
        "equal": f"{indicator} = {value}",
        "between": f"{indicator} 在 {value} 之间",
    }
    return op_map.get(operator, f"{indicator} {operator} {indicator2 or value}")
