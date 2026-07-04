"""技术分析 Agent。

基于经典技术分析理论（均线、MACD、RSI、布林带、KDJ、ADX、形态、背离等）
对用户筛选品种进行自动化分析并给出多空结论。
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator

import pandas as pd

from lib.technical_indicators import calculate_all_indicators
from services.agent.analysis import analyze_trend, composite_score, detect_divergence, detect_patterns
from services.agent.context import AgentContext
from services.agent.core import Agent, AgentEvent, AgentEventType, AgentResult, AgentStatus
from services.agent.data_tools import _get_kline_data, _get_realtime_quote, _get_variety_info
from services.agent.utils import resolve_symbol

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是「期货交流社区」的技术分析专家 Agent。\n"
    "你基于经典技术分析理论（均线、MACD、RSI、布林带、KDJ、ADX、形态识别、背离检测等）\n"
    "对期货品种进行系统化技术分析，给出综合评分和多空结论。\n"
    "\n"
    "规则：\n"
    "1. 分析过程基于数据库 K 线数据，结果客观、可复现\n"
    "2. 综合评分 0-100，>=70 偏强，40-69 震荡，<40 偏弱\n"
    "3. 给出明确的趋势方向、关键支撑/阻力、操作建议\n"
    "4. 所有分析仅供参考，不构成投资建议\n"
)


class TechAnalysisAgent(Agent):
    """技术分析 Agent。

    输入：品种代码 + 周期（默认日线）
    执行：获取 K 线 → 计算指标 → 运行趋势/形态/背离分析 → 综合评分 → 输出报告
    """

    name = "tech_analysis"
    description = "期货技术分析专家，基于经典技术指标给出综合评分和多空结论"

    async def run(self, query: str) -> AgentResult:
        """执行技术分析任务。

        query 格式示例："分析螺纹钢日线走势"、"AU 技术面如何"
        """
        self._add_step("thought", f"开始技术分析：{query}")

        # 从 query 中提取品种代码
        symbol = resolve_symbol(self.context.db, query)

        if not symbol:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message="无法从查询中识别品种代码，请提供品种代码（如 RB、AU）或品种名称",
                steps=self.get_steps(),
            )

        self._add_step("action", f"识别品种：{symbol}")

        db = self.context.db

        # 获取品种信息
        variety_info = _get_variety_info(db, symbol)
        if not variety_info:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=f"未找到品种 {symbol}",
                steps=self.get_steps(),
            )
        self._add_step("observation", f"品种信息：{variety_info['name']} ({variety_info['exchange']})")

        # 获取实时行情
        quote = _get_realtime_quote(db, symbol)
        self._add_step("observation", f"实时行情：{quote}")

        # 获取 K 线数据（日线，最近 120 根）
        kline_data = _get_kline_data(db, symbol, period="1d", limit=120)
        if not kline_data or len(kline_data) < 20:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=f"品种 {symbol} K 线数据不足（需要至少 20 根）",
                steps=self.get_steps(),
            )
        self._add_step("observation", f"获取 K 线数据：{len(kline_data)} 根")

        # 转换为 DataFrame
        df = pd.DataFrame(kline_data)
        df["time"] = pd.to_datetime(df["time"])
        df = df.sort_values("time").reset_index(drop=True)

        # 计算所有指标
        df = calculate_all_indicators(df)
        self._add_step("system", f"计算完成：SMA/EMA/RSI/MACD/BOLL/KDJ/ATR/CCI/OBV/ADX/WR")

        # 运行各分析模块
        trend = analyze_trend(df)
        self._add_step("system", f"趋势分析：{trend['direction']}，强度{trend['strength']}")

        pattern = detect_patterns(df)
        self._add_step("system", f"形态分析：{pattern['pattern']}")

        divergence = detect_divergence(df)
        self._add_step("system", f"背离分析：{divergence['divergence']}")

        # 综合评分
        composite = composite_score(df)
        self._add_step("system", f"综合评分：{composite['score']}/100，评级：{composite['rating']}")

        # 构建结构化报告
        latest = df.iloc[-1]
        latest_bar = kline_data[-1]

        report = {
            "symbol": symbol,
            "name": variety_info["name"],
            "exchange": variety_info["exchange"],
            "current_price": quote.get("current_price") if quote else None,
            "change_percent": quote.get("change_percent") if quote else None,
            "analysis_date": latest_bar["time"],
            "kline_count": len(kline_data),
            "score": composite["score"],
            "rating": composite["rating"],
            "direction": composite["direction"],
            "trend": trend,
            "pattern": pattern,
            "divergence": divergence,
            "details": composite["details"],
            "indicators": {
                "sma5": round(latest.get("sma5", 0), 2) if latest.get("sma5") else None,
                "sma20": round(latest.get("sma20", 0), 2) if latest.get("sma20") else None,
                "sma60": round(latest.get("sma60", 0), 2) if latest.get("sma60") else None,
                "rsi6": round(latest.get("rsi6", 0), 1) if latest.get("rsi6") else None,
                "rsi24": round(latest.get("rsi24", 0), 1) if latest.get("rsi24") else None,
                "macd_dif": round(latest.get("macd_dif", 0), 3) if latest.get("macd_dif") else None,
                "macd_dea": round(latest.get("macd_dea", 0), 3) if latest.get("macd_dea") else None,
                "macd_bar": round(latest.get("macd_bar", 0), 3) if latest.get("macd_bar") else None,
                "boll_upper": round(latest.get("boll_upper", 0), 2) if latest.get("boll_upper") else None,
                "boll_mid": round(latest.get("boll_mid", 0), 2) if latest.get("boll_mid") else None,
                "boll_lower": round(latest.get("boll_lower", 0), 2) if latest.get("boll_lower") else None,
                "kdj_k": round(latest.get("kdj_k", 0), 1) if latest.get("kdj_k") else None,
                "kdj_d": round(latest.get("kdj_d", 0), 1) if latest.get("kdj_d") else None,
                "kdj_j": round(latest.get("kdj_j", 0), 1) if latest.get("kdj_j") else None,
                "atr14": round(latest.get("atr14", 0), 2) if latest.get("atr14") else None,
                "cci14": round(latest.get("cci14", 0), 1) if latest.get("cci14") else None,
                "adx14": round(latest.get("adx14", 0), 1) if latest.get("adx14") else None,
                "dmi_plus": round(latest.get("dmi_plus", 0), 1) if latest.get("dmi_plus") else None,
                "dmi_minus": round(latest.get("dmi_minus", 0), 1) if latest.get("dmi_minus") else None,
                "vol_ratio": round(latest.get("vol_ratio", 0), 2) if latest.get("vol_ratio") else None,
                "wr14": round(latest.get("wr14", 0), 1) if latest.get("wr14") else None,
            },
            "notes": composite["notes"],
        }

        # 生成自然语言总结
        summary_lines = [
            f"## {variety_info['name']} ({symbol}) 技术分析报告",
            "",
            f"**最新价**：{report['current_price']}  **涨跌**：{report['change_percent']}%",
            f"**综合评分**：{composite['score']}/100  **评级**：{composite['rating']}",
            f"**趋势方向**：{trend['direction']}  **强度**：{trend['strength']}",
            "",
            "### 关键指标",
            f"- RSI(24)：{report['indicators']['rsi24']}（>70 超买，<30 超卖）",
            f"- MACD：DIF {report['indicators']['macd_dif']}, DEA {report['indicators']['macd_dea']}, 柱状 {report['indicators']['macd_bar']}",
            f"- KDJ：K {report['indicators']['kdj_k']}, D {report['indicators']['kdj_d']}, J {report['indicators']['kdj_j']}",
            f"- 布林带：上轨 {report['indicators']['boll_upper']}, 中轨 {report['indicators']['boll_mid']}, 下轨 {report['indicators']['boll_lower']}",
            f"- ADX：{report['indicators']['adx14']}（>25 趋势明显，>40 强趋势）",
            f"- 量比：{report['indicators']['vol_ratio']}",
            "",
            "### 分析结论",
            composite["notes"],
            "",
            "> ⚠️ 所有分析仅供参考，不构成投资建议",
        ]

        summary = "\n".join(str(l) for l in summary_lines if l is not None)

        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=summary,
            data=report,
            steps=self.get_steps(),
        )

    async def run_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行技术分析任务。

        由于技术分析为本地确定性计算，先执行完整分析，
        再按步骤 yield 事件，供前端展示执行过程。
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
                content=result.error_message or "分析失败",
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
