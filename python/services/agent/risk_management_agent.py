"""风控 Agent。

基于技术分析或用户策略，生成完整的资金管理和风险控制方案。
包含：仓位管理、止损止盈、回撤控制、交易纪律。
"""

from __future__ import annotations

import logging

import pandas as pd

from lib.technical_indicators import calculate_all_indicators
from services.agent.context import AgentContext
from services.agent.core import Agent, AgentResult, AgentStatus
from services.agent.data_tools import _get_kline_data, _get_realtime_quote, _get_variety_info
from services.agent.risk_management.drawdown_control import generate_risk_management_plan
from services.agent.utils import extract_direction, extract_price, resolve_symbol

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是「期货交流社区」的风险管理专家 Agent。\n"
    "你基于技术分析结果或用户策略，生成完整的交易风控方案。\n"
    "\n"
    "风控方案必须包含：\n"
    "1. 仓位管理：建议手数、资金占用比例\n"
    "2. 止损控制：止损价位、止损距离、触发条件\n"
    "3. 止盈控制：止盈价位、风险收益比、移动止盈方案\n"
    "4. 回撤控制：单日亏损上限、总回撤上限、连续亏损暂停规则\n"
    "5. 交易纪律：加仓/减仓规则、持仓时间建议\n"
    "\n"
    "所有风控方案必须明确数字、可执行。\n"
    "风险提示：所有方案仅供参考，不构成投资建议。\n"
)

_DEFAULT_ACCOUNT_BALANCE = 100000.0  # 默认虚拟资金 10 万


class RiskManagementAgent(Agent):
    """风控管理 Agent。

    输入：品种 + 方向 + 入场价（可选）+ 账户资金（可选）+ 风险偏好（可选）
    输出：完整风控方案
    """

    name = "risk_management"
    description = "期货风险管理专家，生成资金管理、止损止盈、回撤控制方案"

    async def run(self, query: str) -> AgentResult:
        """执行风控方案生成。"""
        self._add_step("thought", f"开始风控分析：{query}")

        db = self.context.db

        # 1. 解析参数
        symbol = resolve_symbol(db, query)
        direction = extract_direction(query) or "long"
        user_entry_price = extract_price(query)

        if not symbol:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message="无法识别品种代码，请提供品种代码（如 RB、AU）或品种名称",
                steps=self.get_steps(),
            )

        self._add_step("action", f"解析参数：品种={symbol}，方向={direction}")

        # 2. 获取品种信息
        variety_info = _get_variety_info(db, symbol)
        if not variety_info:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=f"未找到品种 {symbol}",
                steps=self.get_steps(),
            )
        self._add_step("observation", f"品种信息：{variety_info['name']}")

        # 3. 获取实时行情
        quote = _get_realtime_quote(db, symbol)
        entry_price = user_entry_price or (quote.get("current_price") if quote else None)
        if not entry_price:
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=f"无法获取 {symbol} 当前价格，请提供入场价格",
                steps=self.get_steps(),
            )
        entry_price = float(entry_price)
        self._add_step("observation", f"入场价格：{entry_price}")

        # 4. 获取 K 线数据用于计算 ATR/支撑阻力
        kline_data = _get_kline_data(db, symbol, period="1d", limit=60)
        df = None
        support_levels = []
        resistance_levels = []
        if kline_data and len(kline_data) >= 20:
            df = pd.DataFrame(kline_data)
            df["time"] = pd.to_datetime(df["time"])
            df = df.sort_values("time").reset_index(drop=True)
            df = calculate_all_indicators(df)
            # 提取支撑/阻力（前20日高低点）
            recent = df.iloc[-20:]
            support_levels = [round(recent["low"].min(), 2)]
            resistance_levels = [round(recent["high"].max(), 2)]
            self._add_step("observation", f"K 线数据：{len(kline_data)} 根，支撑位={support_levels[0]}，阻力位={resistance_levels[0]}")
        else:
            self._add_step("observation", "K 线数据不足，使用固定百分比风控")

        # 5. 生成风控方案
        risk_level = "medium"  # 默认中等风险
        if any(w in query for w in ["保守", "低", "谨慎", "conservative"]):
            risk_level = "low"
        elif any(w in query for w in ["激进", "高", "aggressive", "大胆"]):
            risk_level = "high"

        margin_rate = variety_info.get("margin_rate")
        if margin_rate:
            margin_rate = float(margin_rate)

        plan = generate_risk_management_plan(
            account_balance=_DEFAULT_ACCOUNT_BALANCE,
            entry_price=entry_price,
            direction=direction,  # type: ignore[arg-type]
            risk_level=risk_level,  # type: ignore[arg-type]
            margin_rate=margin_rate,
            contract_multiplier=10.0,
            tick_size=1.0,
            df=df,
            support_levels=support_levels,
            resistance_levels=resistance_levels,
        )

        self._add_step("system", f"风控方案生成完成：仓位 {plan.position_sizing['position_size_pct']:.1f}%，止损 {plan.stop_loss['stop_loss_price']}")

        # 6. 构建报告
        sl = plan.stop_loss
        tp = plan.take_profit
        pos = plan.position_sizing
        dd = plan.drawdown_control

        report = {
            "symbol": symbol,
            "name": variety_info["name"],
            "direction": direction,
            "entry_price": entry_price,
            "account_balance": pos["account_balance"],
            "risk_level": risk_level,
            "position": pos,
            "stop_loss": sl,
            "take_profit": tp,
            "drawdown_control": {
                "max_daily_loss_pct": dd.max_daily_loss_pct,
                "max_drawdown_pct": dd.max_drawdown_pct,
                "max_consecutive_losses": dd.max_consecutive_losses,
                "position_size_reduction": dd.position_size_reduction,
                "trading_halt_drawdown": dd.trading_halt_drawdown,
            },
            "daily_limits": plan.daily_limits,
            "total_limits": plan.total_limits,
        }

        # 7. 自然语言总结
        summary_lines = [
            f"## {variety_info['name']} ({symbol}) { '做多' if direction == 'long' else '做空' } 风控方案",
            "",
            f"**入场价格**：{entry_price}  **账户资金**：{pos['account_balance']:.0f}  **风险等级**：{risk_level}",
            "",
            "### 1. 仓位管理",
            f"- 建议仓位：{pos['suggested_lots']:.2f} 手（占用资金 {pos['position_size_pct']:.1f}%）",
            f"- 单次风险：{pos['risk_per_trade_pct']:.1f}%（{pos['risk_amount']:.0f}）",
            f"- 最大允许仓位：{pos['max_position_size_pct']:.1f}%",
        ]
        if pos.get("margin_ratio"):
            summary_lines.append(f"- 保证金占用：{pos['margin_ratio']:.1f}%（{pos['margin_required']:.0f}）")

        summary_lines.extend([
            "",
            "### 2. 止损控制",
            f"- 止损价位：{sl['stop_loss_price']}",
            f"- 止损距离：{sl['risk_distance']:.2f}（{sl['risk_distance_pct']:.1f}%）",
            f"- 止损方法：{sl['method']}",
            "",
            "### 3. 止盈控制",
            f"- 止盈价位：{tp['take_profit_price']}",
            f"- 止盈距离：{tp['reward_distance']:.2f}（{tp['reward_distance_pct']:.1f}%）",
            f"- 风险收益比：1:{tp['risk_reward_ratio']:.2f}",
            f"- 止盈方法：{tp['method']}",
        ])
        if tp.get("trailing_trigger"):
            summary_lines.extend([
                f"- 移动止盈：触发价 {tp['trailing_trigger']}，触发后回撤止盈 {tp['trailing_stop']}",
            ])

        summary_lines.extend([
            "",
            "### 4. 回撤控制",
            f"- 单日最大亏损：{dd.max_daily_loss_pct}%（{plan.daily_limits['max_daily_loss_amount']:.0f}）",
            f"- 总最大回撤：{dd.max_drawdown_pct}%",
            f"- 回撤 {dd.position_size_reduction * 100:.0f}% 时仓位缩减一半",
            f"- 回撤 {dd.trading_halt_drawdown}% 时暂停交易",
            f"- 建议最大连续亏损：{dd.max_consecutive_losses} 次后强制暂停",
            "",
            "### 5. 交易纪律",
            "- 建仓：按建议手数一次性建仓或分 2 批（50% + 50%）",
            "- 加仓：盈利后回撤不超过 30% 时可考虑加仓，加仓量不超过初始仓位 50%",
            "- 减仓：亏损达到单次风险 50% 时减仓 50%",
            "- 持仓监控：每日收盘检查是否触发回撤控制线",
            "- 复盘：连续亏损 3 次或回撤 10% 后必须复盘再交易",
            "",
            "> ⚠️ 所有风控方案仅供参考，不构成投资建议。实际交易请根据自身情况调整。",
        ])

        summary = "\n".join(str(l) for l in summary_lines)

        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=summary,
            data=report,
            steps=self.get_steps(),
        )
