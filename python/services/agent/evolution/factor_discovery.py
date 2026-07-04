"""因子自动发现模块。

Phase 1：模板生成 —— 通过预设的因子模板 + 参数采样生成候选因子池，
          然后通过 IC/Rank IC 筛选 + 去相关过滤，选出 Top-N 因子。

设计原则：
1. 所有生成的因子公式都通过 validate_factor_formula() 安全校验
2. 评估使用现有 factor_engine 的 evaluate_factor / evaluate_factor_performance
3. 不依赖 LLM，纯确定性计算
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from services.agent.factor_engine.data_loader import load_panel_data
from services.agent.factor_engine.dsl import PanelData, evaluate_factor, validate_factor_formula
from services.agent.factor_engine.evaluator import evaluate_factor as evaluate_factor_performance

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 因子模板
# ------------------------------------------------------------------

# 每个模板：公式字符串 + 参数名 → 采样值列表
FACTOR_TEMPLATES: list[tuple[str, dict[str, list[int | float]]]] = [
    # --- 动量类 ---
    ("close / ts_delay(close, {lookback}) - 1", {"lookback": [1, 3, 5, 10, 20, 60]}),
    (
        "ts_mean(close, {fast}) / ts_mean(close, {slow}) - 1",
        {"fast": [3, 5, 10], "slow": [10, 20, 60]},
    ),
    (
        "ts_delta(close, {lookback}) / ts_std(close, {lookback})",
        {"lookback": [10, 20]},
    ),
    # --- 波动率类 ---
    (
        "ts_std(close, {window}) / ts_mean(close, {window})",
        {"window": [5, 10, 20, 60]},
    ),
    (
        "(high - low) / ts_mean(close, {window})",
        {"window": [5, 10, 20]},
    ),
    # --- 量价关系 ---
    ("volume / ts_mean(volume, {window}) - 1", {"window": [5, 20, 60]}),
    ("ts_corr(close, volume, {window})", {"window": [10, 20, 60]}),
    # --- 反转类 ---
    (
        "-1 * (close / ts_delay(close, {lookback}) - 1)",
        {"lookback": [1, 3, 5]},
    ),
    (
        "-1 * ts_zscore(close, {window})",
        {"window": [5, 10, 20]},
    ),
    # --- 突破类 ---
    ("close / ts_max(high, {window}) - 1", {"window": [10, 20, 60, 120]}),
    ("close / ts_min(low, {window}) - 1", {"window": [10, 20, 60, 120]}),
    # --- 趋势强度 ---
    ("ts_rank(close, {window})", {"window": [5, 10, 20, 60]}),
    ("ts_skew(close, {window})", {"window": [10, 20, 60]}),
    ("ts_kurt(close, {window})", {"window": [10, 20, 60]}),
    # --- 复合类 ---
    (
        "ts_mean(close, {fast}) / ts_mean(close, {slow}) * ts_std(volume, {vol_window})",
        {"fast": [5, 10], "slow": [20, 60], "vol_window": [5, 20]},
    ),
]


@dataclass
class FactorCandidate:
    """候选因子。"""

    formula: str
    template_name: str  # 来源模板标识
    params: dict[str, int | float]
    # 评估指标（填充后）
    rank_ic_mean: float | None = None
    rank_icir: float | None = None
    ic_mean: float | None = None
    icir: float | None = None
    coverage: float | None = None
    turnover: float | None = None
    evaluation: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """人类可读的因子标签。"""
        return f"{self.template_name}({self.params})"


def generate_template_factors() -> list[FactorCandidate]:
    """从模板生成所有候选因子。

    Returns:
        候选因子列表（每个参数组合一个）。
    """
    candidates: list[FactorCandidate] = []
    for template, param_space in FACTOR_TEMPLATES:
        param_names = list(param_space.keys())
        param_values = list(param_space.values())

        # 笛卡尔积展开
        from itertools import product

        for combo in product(*param_values):
            params = dict(zip(param_names, combo, strict=False))
            formula = template
            for name, value in params.items():
                formula = formula.replace(f"{{{name}}}", str(value))

            # 安全校验
            try:
                validate_factor_formula(formula)
            except ValueError as exc:
                logger.debug("模板因子公式校验不通过：%s → %s", formula, exc)
                continue

            candidate = FactorCandidate(
                formula=formula,
                template_name=template,
                params=params,
            )
            candidates.append(candidate)

    logger.info("模板生成完成：%d 个通过安全校验", len(candidates))
    return candidates


def evaluate_candidates(
    candidates: list[FactorCandidate],
    db: Session,
    symbols: list[str],
    period: str = "1d",
    min_bars: int = 60,
) -> list[FactorCandidate]:
    """对候选因子进行 IC/Rank IC 评估。

    Args:
        candidates: 候选因子列表。
        db: 数据库会话。
        symbols: 品种代码列表。
        period: K 线周期。
        min_bars: 最少 K 线数。

    Returns:
        评估后的候选因子列表（填充了 rank_ic_mean / icir 等字段）。
    """
    if not candidates:
        return []

    # 加载面板数据
    try:
        panel = load_panel_data(db, symbols=symbols, period=period, min_bars=min_bars)
    except ValueError as exc:
        logger.warning("无法加载面板数据：%s", exc)
        return candidates

    evaluated: list[FactorCandidate] = []
    for candidate in candidates:
        try:
            factor_values = evaluate_factor(candidate.formula, panel)
        except (ValueError, KeyError) as exc:
            logger.debug("因子求值失败 %s：%s", candidate.label, exc)
            continue

        try:
            eval_result = evaluate_factor_performance(
                factor_name=candidate.label,
                formula=candidate.formula,
                factor_values=factor_values,
                panel=panel,
                forward_periods=1,
                n_quantiles=5,
            )
        except Exception as exc:
            logger.debug("因子评估失败 %s：%s", candidate.label, exc)
            continue

        candidate.rank_ic_mean = eval_result.rank_ic_mean
        candidate.rank_icir = eval_result.rank_icir
        candidate.ic_mean = eval_result.ic_mean
        candidate.icir = eval_result.icir
        candidate.coverage = eval_result.coverage
        candidate.turnover = eval_result.turnover
        candidate.evaluation = eval_result.to_dict()

        evaluated.append(candidate)

    logger.info("因子评估完成：%d/%d 个通过", len(evaluated), len(candidates))
    return evaluated


def filter_by_ic(
    candidates: list[FactorCandidate],
    min_abs_rank_ic: float = 0.02,
    min_icir: float = 0.0,
    max_correlation: float = 0.7,
    panel: PanelData | None = None,
    top_n: int = 20,
) -> list[FactorCandidate]:
    """按 IC 质量过滤和去相关，返回 Top-N 因子。

    Args:
        candidates: 评估后的候选因子列表。
        min_abs_rank_ic: Rank IC 绝对值下限。
        min_icir: ICIR 下限（0 表示不过滤）。
        max_correlation: 因子间最大允许相关系数（高于此值被认为冗余）。
        panel: 面板数据（用于计算因子间相关性）。若为 None 则跳过去相关。
        top_n: 最终保留的最大因子数。

    Returns:
        过滤后的 Top-N 因子列表（按 |Rank IC| 降序）。
    """
    # Step 1: IC 初筛
    filtered = []
    none_ic_count = 0
    for c in candidates:
        if c.rank_ic_mean is None:
            none_ic_count += 1
            # 保留少量 None 值因子以备不需要严格 IC 筛选的场景
            if min_abs_rank_ic == 0.0 and min_icir == 0.0:
                filtered.append(c)
            continue

        abs_rank_ic = abs(c.rank_ic_mean or 0)
        icir = abs(c.rank_icir or 0)
        if abs_rank_ic >= min_abs_rank_ic and icir >= min_icir:
            filtered.append(c)

    if none_ic_count > 0:
        logger.info("IC 计算：%d 个因子 IC 为 None（共 %d 个候选）", none_ic_count, len(candidates))

    if not filtered:
        logger.info("IC 初筛后无剩余因子")
        return []

    logger.info(
        "IC 初筛：%d/%d 通过（|Rank IC|≥%.3f，ICIR≥%.1f）", len(filtered), len(candidates), min_abs_rank_ic, min_icir
    )

    # Step 2: 按 |Rank IC| 排序
    filtered.sort(key=lambda c: abs(c.rank_ic_mean or 0), reverse=True)

    # Step 3: 去相关（贪心选择）
    if panel is not None and len(filtered) > 1:
        selected = _dedup_by_correlation(filtered, panel, max_correlation, top_n)
    else:
        selected = filtered[:top_n]

    logger.info("最终选定 %d 个因子（去重 + Top-%d）", len(selected), top_n)
    return selected


def _dedup_by_correlation(
    candidates: list[FactorCandidate],
    panel: PanelData,
    max_correlation: float = 0.7,
    top_n: int = 20,
) -> list[FactorCandidate]:
    """通过因子值相关性去重，贪心选择 Top-N 个低相关的因子。

    策略：按 |Rank IC| 降序遍历，每个新因子与已选定集合中
    所有因子的相关系数必须 < max_correlation。
    """
    selected: list[FactorCandidate] = []
    selected_values: list[pd.DataFrame] = []

    for candidate in candidates:
        # 计算因子值
        try:
            factor_values = evaluate_factor(candidate.formula, panel)
        except (ValueError, KeyError):
            continue

        # 将所有品种的因子值展平用于相关性计算
        flat = factor_values.stack().dropna()

        # 检查与已选因子的相关性
        redundant = False
        for sv in selected_values:
            flat_sv = sv.stack().dropna()
            common_idx = flat.index.intersection(flat_sv.index)
            if len(common_idx) < 20:
                continue
            corr = flat.loc[common_idx].corr(flat_sv.loc[common_idx])
            if abs(corr) >= max_correlation:
                redundant = True
                break

        if not redundant:
            selected.append(candidate)
            selected_values.append(factor_values)

        if len(selected) >= top_n:
            break

    return selected


def discover_factors(
    db: Session,
    symbols: list[str],
    period: str = "1d",
    min_bars: int = 60,
    min_abs_rank_ic: float = 0.02,
    top_n: int = 20,
) -> list[FactorCandidate]:
    """因子自动发现主流程。

    Args:
        db: 数据库会话。
        symbols: 品种代码列表（至少 1 个）。
        period: K 线周期。
        min_bars: 最少 K 线数。
        min_abs_rank_ic: Rank IC 过滤阈值。
        top_n: 最终保留因子数。

    Returns:
        Top-N 候选因子列表（已排序）。
    """
    if not symbols:
        raise ValueError("symbols 不能为空")

    logger.info("因子发现开始：symbols=%s，period=%s", symbols, period)

    # 1. 模板生成
    candidates = generate_template_factors()
    if not candidates:
        logger.warning("模板生成返回空列表")
        return []

    # 2. 评估
    evaluated = evaluate_candidates(candidates, db, symbols, period, min_bars)
    if not evaluated:
        logger.warning("因子评估后无通过项")
        return []

    # 3. 过滤
    # 单品种时 IC 评估无法计算横截面相关性（仅 1 个品种/日期）
    # — 回退到使用所有评估成功的因子，按覆盖率 + 模板多样性选择
    if len(symbols) == 1:
        logger.info("单品种模式：跳过 IC 筛选，按模板多样性选择 Top-%d 因子", top_n)
        evaluated.sort(key=lambda c: c.coverage or 0, reverse=True)
        selected: list[FactorCandidate] = []
        seen_templates: set[str] = set()
        for c in evaluated:
            template_key = c.template_name
            if template_key not in seen_templates or len(selected) < top_n // 2:
                selected.append(c)
                seen_templates.add(template_key)
            if len(selected) >= top_n:
                break
        return selected

    filtered = filter_by_ic(evaluated, min_abs_rank_ic=min_abs_rank_ic, top_n=top_n)

    return filtered
