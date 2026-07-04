"""因子挖掘 Agent。

第一期聚焦「已有因子评估」：用户给定因子公式，Agent 自动加载面板数据、
安全求值、计算 IC/Rank IC/分层回测/最大回撤等指标，并生成解释报告。
"""

from __future__ import annotations

import ast
import logging
import re
from collections.abc import AsyncIterator
from typing import Any

from services.agent.core import Agent, AgentEvent, AgentEventType, AgentResult, AgentStatus
from services.agent.factor_engine.data_loader import extract_factor_universe, load_panel_data
from services.agent.factor_engine.dsl import evaluate_factor, validate_factor_formula
from services.agent.factor_engine.evaluator import evaluate_factor as evaluate_factor_performance
from services.data_catalog import DataCatalogService

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "你是「期货交流社区」的因子研究专家 Agent。\n"
    "你负责评估用户提供的期货因子公式，计算其预测有效性。\n"
    "评估维度包括 IC、Rank IC、ICIR、分层回测收益、多空收益、最大回撤、换手率、覆盖率。\n"
    "所有结论必须基于数据，不夸大有效性，并提示过拟合风险。\n"
)


# 预设因子解释模板
_FACTOR_EXPLANATION_TEMPLATES: dict[str, str] = {
    "momentum": "该因子衡量价格动量，高动量品种可能延续趋势。",
    "reversal": "该因子衡量价格反转，低值品种可能反弹。",
    "volume_price": "该因子衡量价量关系，异常放量可能预示方向变化。",
    "volatility": "该因子衡量波动率，高波动通常伴随高风险。",
}

_SUPPORTED_PANEL_FIELDS = {"open", "high", "low", "close", "volume"}
_KNOWN_DATA_FIELDS = _SUPPORTED_PANEL_FIELDS | {"amount", "open_interest", "turnover_rate"}


def _extract_formula(query: str) -> str | None:
    """从用户查询中提取因子公式。

    优先匹配引号内的内容，其次匹配包含 close/open/high/low/volume 的数学表达式。
    """
    # 1. 引号内内容
    quoted = re.findall(r'["""]([^"""]+)["""]', query)
    if not quoted:
        quoted = re.findall(r"[''']([^''']+)[''']", query)
    if not quoted:
        quoted = re.findall(r'"([^"]+)"', query)
    if not quoted:
        quoted = re.findall(r"'([^']+)'", query)
    if quoted:
        return quoted[0].strip()

    # 2. 寻找包含面板字段和算子的表达式
    # 简单启发式：从第一个面板字段开始截取到句子结束或特定标点
    field_pattern = r"\b(open|high|low|close|volume)\b"
    match = re.search(field_pattern, query, re.IGNORECASE)
    if match:
        start = match.start()
        # 截取到常见终止符
        end_match = re.search(r"[。，；！？\n]", query[start:])
        end = start + end_match.start() if end_match else len(query)
        return query[start:end].strip()

    return None


def _factor_category_hint(formula: str) -> str:
    """根据公式给出简单的因子类别提示。"""
    formula_lower = formula.lower()
    if "volume" in formula_lower and "close" in formula_lower:
        return _FACTOR_EXPLANATION_TEMPLATES["volume_price"]
    if "ts_std" in formula_lower or "ts_mean" in formula_lower or "atr" in formula_lower:
        return _FACTOR_EXPLANATION_TEMPLATES["volatility"]
    if ("ts_delay" in formula_lower or "ts_delta" in formula_lower) and "-" in formula and "1" in formula:
        return _FACTOR_EXPLANATION_TEMPLATES["momentum"]
    return "该因子综合了价格和/或成交量信息，请结合评估指标判断其有效性。"


def _extract_required_data_fields(formula: str) -> set[str]:
    """提取因子公式直接引用的数据字段。"""
    try:
        tree = ast.parse(formula.strip(), mode="eval")
    except SyntaxError:
        return set()
    fields: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in _KNOWN_DATA_FIELDS:
            fields.add(node.id)
    return fields


class FactorMiningAgent(Agent):
    """因子挖掘 Agent（已有因子评估版）。"""

    name = "factor_mining"
    description = "期货因子评估专家，支持用户给定因子的 IC、分层回测、回撤等评估"

    async def run(self, query: str) -> AgentResult:
        """执行因子评估任务。"""
        self._add_step("thought", f"开始因子评估：{query}")

        # 1. 提取公式
        formula = _extract_formula(query)
        if not formula:
            error_message = '无法从查询中提取因子公式，请使用引号包裹公式，例如：评估 "close / ts_delay(close, 5) - 1" 在黑色系的表现'
            self._add_step("error", error_message)
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=error_message,
                steps=self.get_steps(),
            )
        self._add_step("action", f"提取因子公式：{formula}")

        catalog = DataCatalogService(self.context.db)
        datasets = catalog.list_available_datasets()
        required_fields = _extract_required_data_fields(formula)
        missing_fields = sorted(required_fields - _SUPPORTED_PANEL_FIELDS)
        self._add_step(
            "action",
            "因子评估前读取 Data Catalog 并检查字段",
            tool_name="DataCatalogService.list_available_datasets",
            tool_output={
                "dataset_count": len(datasets),
                "required_fields": sorted(required_fields),
                "supported_panel_fields": sorted(_SUPPORTED_PANEL_FIELDS),
            },
        )
        if missing_fields:
            error_message = (
                "因子公式需要当前因子面板尚未提供的字段："
                f"{', '.join(missing_fields)}。请先接入数据宽表或改用 open/high/low/close/volume。"
            )
            self._add_step("error", error_message)
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=error_message,
                data={
                    "data_preflight": {
                        "datasets": [item["dataset_name"] for item in datasets],
                        "required_fields": sorted(required_fields),
                        "missing_fields": missing_fields,
                    }
                },
                steps=self.get_steps(),
            )

        # 2. 校验公式安全
        try:
            validate_factor_formula(formula)
            self._add_step("system", "因子公式通过安全校验")
        except ValueError as e:
            error_message = f"因子公式校验失败：{e}"
            self._add_step("error", error_message)
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=error_message,
                steps=self.get_steps(),
            )

        # 3. 解析品种池
        db = self.context.db
        symbols, category = extract_factor_universe(query, db)
        self._add_step(
            "action",
            f"确定评估范围：symbols={symbols}，category={category}",
        )

        coverage_checks = self._check_factor_data_coverage(catalog, symbols=symbols, category=category, period="1d")
        blocking_checks = [item for item in coverage_checks if item["status"] == "bad"]
        if blocking_checks:
            error_message = "因子评估前数据检查失败：" + "；".join(
                f"{item['symbol']} 缺少可用 K 线数据" for item in blocking_checks[:3]
            )
            self._add_step("error", error_message)
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=error_message,
                data={"data_preflight": {"coverage_checks": coverage_checks}},
                steps=self.get_steps(),
            )
        warning_checks = [item for item in coverage_checks if item["status"] == "warning"]
        if warning_checks:
            self._add_step(
                "observation",
                f"因子评估数据覆盖存在 warning：{len(warning_checks)} 个品种样本偏少，继续评估并保留风险提示",
                tool_name="DataCatalogService.get_symbol_data_coverage",
                tool_output={"warnings": warning_checks},
            )

        # 4. 加载面板数据
        try:
            panel = load_panel_data(
                db,
                symbols=symbols,
                category=category,
                period="1d",
                min_bars=30,
            )
            self._add_step(
                "observation",
                f"加载面板数据：{len(panel.close)} 个交易日 × {len(panel.close.columns)} 个品种",
            )
        except ValueError as e:
            error_message = f"数据加载失败：{e}"
            self._add_step("error", error_message)
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=error_message,
                steps=self.get_steps(),
            )

        # 5. 计算因子值
        try:
            factor_values = evaluate_factor(formula, panel)
            self._add_step("system", "因子值计算完成")
        except ValueError as e:
            error_message = f"因子求值失败：{e}"
            self._add_step("error", error_message)
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=error_message,
                steps=self.get_steps(),
            )

        # 6. 评估因子
        try:
            eval_result = evaluate_factor_performance(
                factor_name="用户因子",
                formula=formula,
                factor_values=factor_values,
                panel=panel,
                forward_periods=1,
                n_quantiles=5,
            )
            self._add_step("system", "因子评估完成")
        except Exception as e:
            error_message = f"因子评估失败：{e}"
            self._add_step("error", error_message)
            return AgentResult(
                status=AgentStatus.FAILED,
                error_message=error_message,
                steps=self.get_steps(),
            )

        # 7. 生成报告
        report = eval_result.to_dict()
        report["data_preflight"] = {
            "datasets": [item["dataset_name"] for item in datasets],
            "required_fields": sorted(required_fields),
            "coverage_checks": coverage_checks,
        }
        summary = self._build_summary(formula, eval_result)
        if warning_checks:
            summary += "\n\n### 数据检查\n" + "\n".join(
                f"- {item['symbol']} 覆盖样本 {item['row_count']} 根，低于建议值，结果稳定性需谨慎。"
                for item in warning_checks[:5]
            )

        return AgentResult(
            status=AgentStatus.COMPLETED,
            answer=summary,
            data=report,
            steps=self.get_steps(),
        )

    def _check_factor_data_coverage(
        self,
        catalog: DataCatalogService,
        symbols: list[str] | None,
        category: str | None,
        period: str,
    ) -> list[dict[str, Any]]:
        """在加载因子面板前检查 K 线覆盖。"""
        checks: list[dict[str, Any]] = []
        if not symbols:
            if category:
                profile = catalog.get_dataset_profile("kline_data", include_columns=False)
                self._add_step(
                    "observation",
                    f"因子品种池为 {category}，使用 kline_data 目录摘要作为覆盖预检",
                    tool_name="DataCatalogService.get_dataset_profile",
                    tool_output=profile,
                )
            return checks

        for symbol in symbols:
            coverage = catalog.get_symbol_data_coverage(symbol, period=period)
            kline = coverage["datasets"]["kline_data"]
            row_count = int(kline.get("row_count") or 0)
            if row_count <= 0:
                status = "bad"
            elif row_count < 30:
                status = "warning"
            else:
                status = "good"
            checks.append(
                {
                    "symbol": coverage["symbol"],
                    "period": coverage["period"],
                    "status": status,
                    "row_count": row_count,
                    "first_date": kline.get("first_date"),
                    "last_date": kline.get("last_date"),
                }
            )

        self._add_step(
            "action",
            "因子评估前检查品种 K 线覆盖",
            tool_name="DataCatalogService.get_symbol_data_coverage",
            tool_input={"symbols": symbols, "period": period},
            tool_output={"coverage_checks": checks},
        )
        return checks

    async def run_stream(self, query: str) -> AsyncIterator[dict[str, Any]]:
        """流式执行因子评估。

        通过后台任务执行 run()，将 _add_step 记录的步骤实时推送到进度队列并 yield。
        """
        async for event in self._stream_run(query):
            yield event

    @staticmethod
    def _map_role_to_event_type(role: str) -> AgentEventType:
        mapping = {
            "thought": AgentEventType.THOUGHT,
            "action": AgentEventType.ACTION,
            "observation": AgentEventType.OBSERVATION,
            "system": AgentEventType.THOUGHT,
            "error": AgentEventType.ERROR,
        }
        return mapping.get(role, AgentEventType.THOUGHT)

    def _build_summary(self, formula: str, result: Any) -> str:
        """生成 Markdown 评估报告。"""
        lines = [
            "## 因子评估报告",
            "",
            f"**因子公式**：`{formula}`",
            f"**评估品种**：{', '.join(result.symbols) if result.symbols else '—'}",
            f"**评估区间**：{result.start_date} 至 {result.end_date}（{result.periods} 个交易日）",
            "",
            "### 因子含义",
            _factor_category_hint(formula),
            "",
            "### 有效性指标",
        ]

        def _fmt(v: float | None, fmt: str = ".3f") -> str:
            return f"{v:{fmt}}" if v is not None else "—"

        lines.extend(
            [
                f"- IC 均值：{_fmt(result.ic_mean)}（ICIR：{_fmt(result.icir)}）",
                f"- Rank IC 均值：{_fmt(result.rank_ic_mean)}（ICIR：{_fmt(result.rank_icir)}）",
                f"- IC 正相关比例：{_fmt(result.ic_positive_ratio, '.1%')}",
                f"- Rank IC 正相关比例：{_fmt(result.rank_ic_positive_ratio, '.1%')}",
                "",
                "### 分层回测",
            ]
        )

        if result.quantile_returns:
            for i, ret in enumerate(result.quantile_returns, start=1):
                lines.append(f"- 第 {i} 层（最低 → 最高）：{_fmt(ret, '.2%')}")
        else:
            lines.append("- 分层回测数据不足")

        lines.extend(
            [
                "",
                "### 多空组合",
                f"- 累计收益：{_fmt(result.long_short_return, '.2%')}",
                f"- 年化收益：{_fmt(result.long_short_annual_return, '.2%')}",
                f"- 最大回撤：{_fmt(result.long_short_max_drawdown, '.2%')}",
                f"- Sharpe：{_fmt(result.long_short_sharpe)}",
                "",
                "### 其他统计",
                f"- 换手率：{_fmt(result.turnover, '.2%')}",
                f"- 覆盖率：{_fmt(result.coverage, '.1%')}",
                "",
                "### 结论与风险提示",
            ]
        )

        # 自动生成简单结论
        conclusion_parts = []
        if result.rank_ic_mean is not None:
            if abs(result.rank_ic_mean) > 0.05:
                direction = "正向" if result.rank_ic_mean > 0 else "负向"
                conclusion_parts.append(
                    f"Rank IC 绝对值 {abs(result.rank_ic_mean):.3f}，显示该因子与未来收益存在较明显的{direction}预测能力。"
                )
            elif abs(result.rank_ic_mean) > 0.02:
                conclusion_parts.append(f"Rank IC 为 {result.rank_ic_mean:.3f}，显示该因子有弱预测能力。")
            else:
                conclusion_parts.append("Rank IC 接近 0，该因子在当前品种池上预测能力较弱。")

        if result.long_short_return is not None:
            if result.long_short_return > 0:
                conclusion_parts.append(f"多空组合累计收益为正（{result.long_short_return:.2%}），分层单调性较好。")
            else:
                conclusion_parts.append(
                    f"多空组合累计收益为负（{result.long_short_return:.2%}），需警惕方向或品种适配问题。"
                )

        if result.coverage is not None and result.coverage < 0.8:
            conclusion_parts.append(f"覆盖率仅 {result.coverage:.1%}，因子存在较多缺失值，可能影响稳定性。")

        if not conclusion_parts:
            conclusion_parts.append("数据不足，无法给出明确结论。")

        lines.append(" ".join(conclusion_parts))
        lines.extend(
            [
                "",
                "> ⚠️ 以上评估基于历史数据，存在过拟合风险，不构成投资建议。",
            ]
        )

        return "\n".join(lines)
