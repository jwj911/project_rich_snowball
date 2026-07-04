"""风控 Agent。

基于技术分析或用户策略，生成完整的资金管理和风险控制方案。
包含：仓位管理、止损止盈、回撤控制、交易纪律。
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import pandas as pd

from lib.technical_indicators import calculate_all_indicators
from services.agent.core import Agent, AgentEvent, AgentEventType, AgentResult, AgentStatus
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

_DEFAULT_ACCOUNT_BALANCE = 100000.0  # 默认虚拟资金 10 万（无持仓记录时使用）


def _load_position_context(db, user_id: int, symbol: str | None) -> dict[str, Any]:
    """从 trade_records 表加载用户当前持仓上下文。

    Returns:
        {
            "account_balance": float,  # 账户权益（净值）
            "initial_balance": float,   # 初始资金（取回测/策略配置，否则默认）
            "open_positions": [...],    # 当前持仓列表
            "total_floating_pnl": float,# 总浮动盈亏
            "total_drawdown_pct": float,# 当前回撤比例
            "has_positions": bool,
        }
    """
    context = {
        "account_balance": _DEFAULT_ACCOUNT_BALANCE,
        "initial_balance": _DEFAULT_ACCOUNT_BALANCE,
        "open_positions": [],
        "total_floating_pnl": 0.0,
        "total_drawdown_pct": 0.0,
        "has_positions": False,
    }

    try:
        from sqlalchemy import text

        # 查询用户未平仓的 trade_records
        rows = (
            db.execute(
                text(
                    "SELECT id, symbol, direction, entry_price, quantity, "
                    "stop_loss_price, take_profit_price, created_at, notes "
                    "FROM trade_records "
                    "WHERE user_id = :uid AND status = 'open' "
                    "ORDER BY created_at DESC"
                ),
                {"uid": user_id},
            )
            .mappings()
            .all()
        )

        if not rows:
            return context

        positions = [dict(r) for r in rows]
        if symbol:
            # 过滤指定品种的持仓（优先级：指定品种 > 全部）
            filtered = [p for p in positions if p["symbol"] and p["symbol"].upper() == symbol.upper()]
            if filtered:
                positions = filtered

        # 获取最新行情计算浮动盈亏
        total_pnl = 0.0
        for pos in positions:
            sym = pos.get("symbol", "")
            if not sym:
                continue
            quote_row = (
                db.execute(
                    text(
                        "SELECT r.current_price FROM realtime_quotes r "
                        "JOIN varieties v ON r.variety_id = v.id "
                        "WHERE v.symbol = :sym AND v.is_active IS TRUE"
                    ),
                    {"sym": sym},
                )
                .mappings()
                .first()
            )

            current_price = float(quote_row["current_price"]) if quote_row else float(pos.get("entry_price", 0))
            entry_price = float(pos.get("entry_price", 0))
            quantity = int(pos.get("quantity", 1))
            direction = pos.get("direction", "long")

            if direction == "long":
                pnl = (current_price - entry_price) * quantity * 10  # multiplier=10
            else:
                pnl = (entry_price - current_price) * quantity * 10
            pos["_current_price"] = current_price
            pos["_floating_pnl"] = round(pnl, 2)
            total_pnl += pnl

        # 查找该用户是否设置过初始资金（从 strategies 或 backtest_runs 推断）
        initial_balance = _DEFAULT_ACCOUNT_BALANCE
        try:
            strategy_row = (
                db.execute(
                    text(
                        "SELECT initial_capital FROM strategies WHERE user_id = :uid ORDER BY updated_at DESC LIMIT 1"
                    ),
                    {"uid": user_id},
                )
                .mappings()
                .first()
            )
            if strategy_row and strategy_row.get("initial_capital"):
                initial_balance = float(strategy_row["initial_capital"])
        except Exception:
            pass

        account_balance = initial_balance + total_pnl
        drawdown_pct = max(0.0, (initial_balance - account_balance) / initial_balance * 100) if total_pnl < 0 else 0.0

        return {
            "account_balance": round(max(account_balance, initial_balance * 0.5), 2),
            "initial_balance": initial_balance,
            "open_positions": positions,
            "total_floating_pnl": round(total_pnl, 2),
            "total_drawdown_pct": round(drawdown_pct, 2),
            "has_positions": True,
        }
    except Exception:
        logger.exception("Failed to load position context, using defaults")
        return context


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
            self._add_step(
                "observation",
                f"K 线数据：{len(kline_data)} 根，支撑位={support_levels[0]}，阻力位={resistance_levels[0]}",
            )
        else:
            self._add_step("observation", "K 线数据不足，使用固定百分比风控")

        # 5. 加载用户持仓上下文
        pos_ctx = _load_position_context(db, self.context.user_id, symbol)
        account_balance = pos_ctx["account_balance"]
        if pos_ctx["has_positions"]:
            self._add_step(
                "observation",
                f"检测到现有持仓：{len(pos_ctx['open_positions'])} 个，"
                f"浮动盈亏 {pos_ctx['total_floating_pnl']:+,.2f}，"
                f"当前权益 {account_balance:,.0f}",
            )

        # 6. 生成风控方案
        risk_level = "medium"  # 默认中等风险
        if any(w in query for w in ["保守", "低", "谨慎", "conservative"]):
            risk_level = "low"
        elif any(w in query for w in ["激进", "高", "aggressive", "大胆"]):
            risk_level = "high"

        margin_rate = variety_info.get("margin_rate")
        if margin_rate:
            margin_rate = float(margin_rate)

        plan = generate_risk_management_plan(
            account_balance=account_balance,
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

        self._add_step(
            "system",
            f"风控方案生成完成：仓位 {plan.position_sizing['position_size_pct']:.1f}%，止损 {plan.stop_loss['stop_loss_price']}",
        )

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
            "initial_balance": pos_ctx["initial_balance"],
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
            "position_context": {
                "has_positions": pos_ctx["has_positions"],
                "open_positions": pos_ctx["open_positions"],
                "total_floating_pnl": pos_ctx["total_floating_pnl"],
                "total_drawdown_pct": pos_ctx["total_drawdown_pct"],
            },
        }

        # 7. 自然语言总结
        summary_lines = [
            f"## {variety_info['name']} ({symbol}) {'做多' if direction == 'long' else '做空'} 风控方案",
            "",
            f"**入场价格**：{entry_price}  **账户权益**：{pos['account_balance']:.0f}  **风险等级**：{risk_level}",
        ]
        if pos_ctx["has_positions"]:
            summary_lines.extend(
                [
                    f"**现有持仓**：{len(pos_ctx['open_positions'])} 个，浮动盈亏 {pos_ctx['total_floating_pnl']:+,.2f}",
                    f"**初始资金**：{pos_ctx['initial_balance']:.0f}，当前回撤 {pos_ctx['total_drawdown_pct']:.1f}%",
                ]
            )
        summary_lines.extend(["", "### 1. 仓位管理"])
        summary_lines.extend(
            [
                f"- 建议仓位：{pos['suggested_lots']:.2f} 手（占用资金 {pos['position_size_pct']:.1f}%）",
                f"- 单次风险：{pos['risk_per_trade_pct']:.1f}%（{pos['risk_amount']:.0f}）",
                f"- 最大允许仓位：{pos['max_position_size_pct']:.1f}%",
            ]
        )
        if pos.get("margin_ratio"):
            summary_lines.append(f"- 保证金占用：{pos['margin_ratio']:.1f}%（{pos['margin_required']:.0f}）")

        summary_lines.extend(
            [
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
            ]
        )
        if tp.get("trailing_trigger"):
            summary_lines.extend(
                [
                    f"- 移动止盈：触发价 {tp['trailing_trigger']}，触发后回撤止盈 {tp['trailing_stop']}",
                ]
            )

        summary_lines.extend(
            [
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
            ]
        )

        summary = "\n".join(str(line) for line in summary_lines)

        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=summary,
            data=report,
            steps=self.get_steps(),
        )

    async def run_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行风控方案生成任务。

        风控计算为本地确定性计算，先执行完整分析，再按步骤 yield 事件。
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
                content=result.error_message or "风控方案生成失败",
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
