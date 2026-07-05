"""因子自动发现模块。

Phase 1：模板生成 —— 通过预设的因子模板 + 参数采样生成候选因子池，
          然后通过 IC/Rank IC 筛选 + 去相关过滤，选出 Top-N 因子。
Phase 2B：遗传编程 —— 表达式树随机生成 + 交叉/变异探索新颖因子组合。

设计原则：
1. 所有生成的因子公式都通过 validate_factor_formula() 安全校验
2. 评估使用现有 factor_engine 的 evaluate_factor / evaluate_factor_performance
3. 不依赖 LLM，纯确定性计算
"""

from __future__ import annotations

import logging
import random
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

# ------------------------------------------------------------------
# GP 因子生成 — 终结符与函数
# ------------------------------------------------------------------

# 终结符：不含参数的基础数据字段
GP_TERMINALS: list[str] = ["open", "high", "low", "close", "volume"]

# 一元时间序列函数：(函数名, 参数范围)
GP_UNARY_TS: list[tuple[str, list[int]]] = [
    ("ts_delay", [1, 3, 5, 10, 20, 60]),
    ("ts_delta", [3, 5, 10, 20, 60]),
    ("ts_mean", [3, 5, 10, 20, 60, 120]),
    ("ts_std", [5, 10, 20, 60]),
    ("ts_rank", [5, 10, 20, 60]),
    ("ts_zscore", [5, 10, 20, 60]),
    ("ts_max", [5, 10, 20, 60, 120]),
    ("ts_min", [5, 10, 20, 60, 120]),
    ("ts_skew", [10, 20, 60]),
    ("ts_kurt", [10, 20, 60]),
    ("ts_rank_pct", [5, 10, 20, 60]),
    ("ts_mad", [5, 10, 20, 60]),
    ("ts_sum", [5, 10, 20]),
    ("ts_median", [5, 10, 20, 60]),
]

# 一元无参函数
GP_UNARY_NOPARAM: list[str] = [
    "abs",
    "log",
    "sqrt",
    "sign",
    "rank",
    "zscore",
]

# 二元时间序列函数
GP_BINARY_TS: list[tuple[str, list[int]]] = [
    ("ts_corr", [10, 20, 60]),
    ("ts_cov", [10, 20, 60]),
    ("ts_regression_beta", [20, 60]),
]

# 算术运算符
GP_ARITHMETIC: list[str] = ["+", "-", "*", "/"]


def _random_terminal() -> str:
    """随机选择一个终结符。"""
    return random.choice(GP_TERMINALS)


def _random_unary_call() -> str:
    """随机生成一个一元函数调用表达式。"""
    if random.random() < 0.6:
        # 时间序列一元函数
        fn, windows = random.choice(GP_UNARY_TS)
        window = random.choice(windows)
    else:
        # 无参一元函数
        fn = random.choice(GP_UNARY_NOPARAM)
        window = None

    arg = _random_terminal() if random.random() < 0.4 else _random_unary_call()

    if window is not None:
        return f"{fn}({arg}, {window})"
    else:
        return f"{fn}({arg})"


def _random_binary_call() -> str:
    """随机生成一个二元函数调用表达式。"""
    if random.random() < 0.5:
        # 时间序列二元函数
        fn, windows = random.choice(GP_BINARY_TS)
        window = random.choice(windows)

        arg1 = _random_terminal() if random.random() < 0.5 else _random_unary_call()
        arg2 = _random_terminal() if random.random() < 0.5 else _random_unary_call()

        return f"{fn}({arg1}, {arg2}, {window})"
    else:
        # 算术运算
        op = random.choice(GP_ARITHMETIC)

        if random.random() < 0.5:
            left = _random_terminal()
        elif random.random() < 0.7:
            left = _random_unary_call()
        else:
            left = _random_binary_call()

        if random.random() < 0.5:
            right = _random_terminal()
        elif random.random() < 0.7:
            right = _random_unary_call()
        else:
            right = _random_binary_call()

        return f"({left} {op} {right})"


def generate_random_factor(max_depth: int = 3) -> str:
    """随机生成一棵表达式树，返回合法因子公式字符串。

    深度控制：
    - depth=1: 仅终结符或一元调用
    - depth=2: 一元调用嵌套 或 二元运算
    - depth=3: 更深嵌套

    Args:
        max_depth: 最大树深度（1-4）。

    Returns:
        因子公式字符串。
    """
    depth = random.randint(1, min(max_depth, 4))

    if depth == 1:
        # 浅层：终结符 或 简单一元函数
        if random.random() < 0.3:
            return _random_terminal()
        else:
            return _random_unary_call()
    elif depth == 2:
        # 中层
        r = random.random()
        if r < 0.3:
            return _random_unary_call()
        elif r < 0.7:
            return _random_binary_call()
        else:
            # 一元(unary_call) — 嵌套
            fn, windows = random.choice(GP_UNARY_TS)
            window = random.choice(windows)
            return f"{fn}({_random_unary_call()}, {window})"
    else:
        # depth >= 3: 复杂树
        r = random.random()
        if r < 0.4:
            return _random_binary_call()
        elif r < 0.7:
            fn, windows = random.choice(GP_UNARY_TS)
            window = random.choice(windows)
            return f"{fn}({_random_binary_call()}, {window})"
        else:
            # 更复杂的嵌套二元表达式
            left = _random_binary_call()
            op = random.choice(GP_ARITHMETIC)
            right = _random_unary_call()
            return f"({left} {op} {right})"


def generate_gp_factors(
    n_generate: int = 100,
    max_depth: int = 3,
    max_attempts: int = 500,
) -> list[FactorCandidate]:
    """通过遗传编程随机生成候选因子。

    生成 n_generate 个随机因子，通过 validate_factor_formula() 校验后返回。

    Args:
        n_generate: 目标生成数量。
        max_depth: 表达式树最大深度。
        max_attempts: 最大尝试次数（防止无限循环）。

    Returns:
        通过校验的候选因子列表。
    """
    candidates: list[FactorCandidate] = []
    seen_formulas: set[str] = set()
    attempts = 0

    while len(candidates) < n_generate and attempts < max_attempts:
        attempts += 1
        formula = generate_random_factor(max_depth)

        if formula in seen_formulas:
            continue

        try:
            validate_factor_formula(formula)
        except ValueError as exc:
            logger.debug("GP 因子校验不通过：%s → %s", formula, exc)
            continue

        seen_formulas.add(formula)
        candidate = FactorCandidate(
            formula=formula,
            template_name="gp_generated",
            params={"depth": max_depth},
        )
        candidates.append(candidate)

    logger.info("GP 因子生成完成：%d 个通过安全校验（尝试 %d 次）", len(candidates), attempts)
    return candidates


def crossover_factor_formula(
    formula_a: str,
    formula_b: str,
) -> str | None:
    """因子公式交叉：将两个公式中的子表达式进行交换。

    策略：在操作符位置进行切割和拼接。
    简化实现：随机选取两个公式中的数值参数，交换后重新组成。
    对于无法解析的复杂公式，回退到简单的参数交换。

    Args:
        formula_a: 父本公式 A。
        formula_b: 父本公式 B。

    Returns:
        交叉后的新公式，如果无法交叉则返回 None。
    """
    # 提取两个公式中的数值参数
    import re

    nums_a = re.findall(r"\b(\d+)\b", formula_a)
    nums_b = re.findall(r"\b(\d+)\b", formula_b)

    if not nums_a or not nums_b:
        return None

    # 随机选择一个参数位置进行交换
    swap_a = random.choice(nums_a)
    swap_b = random.choice(nums_b)

    # 在 A 中交换一个参数值（仅限函数参数，避免破坏结构）
    # 安全做法：只替换窗口参数的值
    new_formula = formula_a.replace(f", {swap_a})", ", __SWAP__)", 1)
    new_formula = new_formula.replace(f", {swap_b})", f", {swap_a})", 1)
    new_formula = new_formula.replace(", __SWAP__)", f", {swap_b})", 1)

    if new_formula == formula_a:
        return None

    try:
        validate_factor_formula(new_formula)
        return new_formula
    except ValueError:
        return None


def mutate_factor_formula(
    formula: str,
    mutation_strength: float = 0.3,
) -> str | None:
    """对因子公式进行变异。

    变异类型：
    1. 窗口参数微调（±1 到 ±50%，以步长 5/10 调整）
    2. 替换一元函数名
    3. 替换终结符
    4. 添加/移除一元包装

    Args:
        formula: 原始公式。
        mutation_strength: 变异幅度。

    Returns:
        变异后的新公式，如果变异失败则返回 None。
    """
    import re

    mutation_type = random.choice(["param", "function", "terminal", "wrap_unary"])

    if mutation_type == "param":
        # 微调一个数值参数
        nums = re.findall(r"\b(\d+)\b", formula)
        if not nums:
            return None
        target = random.choice(nums)
        old_val = int(target)
        # 按比例微调，步长取 5 或 10
        delta_pct = random.uniform(-mutation_strength, mutation_strength) * 2
        step = random.choice([5, 10])
        delta = int(round(old_val * delta_pct / step)) * step
        new_val = max(1, min(250, old_val + delta))
        if new_val == old_val:
            new_val = old_val + (step if random.random() < 0.5 else -step)
            new_val = max(1, min(250, new_val))

        # 只替换作为函数参数的数值（用前后上下文判断）
        new_formula = formula.replace(f", {old_val})", f", {new_val})", 1)

    elif mutation_type == "function":
        # 替换一个一元函数名
        unary_names = [fn for fn, _ in GP_UNARY_TS] + GP_UNARY_NOPARAM
        old_fn = random.choice(unary_names)
        if old_fn not in formula:
            return None
        new_fn = random.choice([n for n in unary_names if n != old_fn])
        # 边界匹配替换函数名
        new_formula = re.sub(rf"\b{re.escape(old_fn)}\b", new_fn, formula, count=1)

    elif mutation_type == "terminal":
        # 替换一个终结符
        for term in GP_TERMINALS:
            if term in formula:
                new_term = random.choice([t for t in GP_TERMINALS if t != term])
                new_formula = re.sub(rf"\b{re.escape(term)}\b", new_term, formula, count=1)
                break
        else:
            return None

    elif mutation_type == "wrap_unary":
        # 用一元函数包装一个子表达式，或去除已有的包装
        if random.random() < 0.5:
            # 添加包装
            fn, windows = random.choice(GP_UNARY_TS)
            window = random.choice(windows)
            # 在公式的某个位置（如终结符）外面包一层 ts_fn(..., window)
            for term in GP_TERMINALS:
                if term in formula:
                    new_formula = formula.replace(term, f"{fn}({term}, {window})", 1)
                    break
            else:
                return None
        else:
            # 去除一层包装：ts_fn(X, N) → X
            pattern = r"(ts_\w+)\(([^,]+),\s*\d+\)"
            m = re.search(pattern, formula)
            if not m:
                return None
            inner = m.group(2).strip()
            new_formula = formula[: m.start()] + inner + formula[m.end() :]
    else:
        return None

    if new_formula == formula:
        return None

    try:
        validate_factor_formula(new_formula)
        return new_formula
    except ValueError:
        return None


def evolve_factor_pool(
    template_factors: list[FactorCandidate],
    n_gp: int = 80,
    gp_generations: int = 3,
    population_size: int = 40,
    crossover_rate: float = 0.7,
    mutation_rate: float = 0.3,
) -> list[FactorCandidate]:
    """通过 GP 进化生成额外因子并与模板因子合并。

    流程：
    1. 随机生成 n_gp 个 GP 因子作为初始种群
    2. 进化 gp_generations 代：选择 → 交叉 → 变异
    3. 将 GP 进化后的因子与模板因子合并去重
    4. 返回合并后的因子池

    Args:
        template_factors: 模板生成的因子列表。
        n_gp: GP 初始生成数量。
        gp_generations: GP 进化代数。
        population_size: GP 种群大小。
        crossover_rate: 交叉概率。
        mutation_rate: 变异概率。

    Returns:
        合并去重后的因子池。
    """
    if n_gp <= 0:
        return list(template_factors)

    # 1. 初始化 GP 种群
    gp_population = generate_gp_factors(n_generate=n_gp)

    if not gp_population:
        logger.warning("GP 因子初始生成失败，仅使用模板因子")
        return list(template_factors)

    # 2. 进化（无评估的选择机制：按公式长度和多样性）
    for gen in range(gp_generations):
        # 按公式简洁性 + 多样性排序
        sorted_pop = sorted(gp_population, key=lambda f: abs(len(f.formula) - 40))

        # 保留 Top-N
        survivors = sorted_pop[:population_size] if len(sorted_pop) > population_size else sorted_pop

        next_gen: list[FactorCandidate] = list(survivors)

        # 生成后代
        while len(next_gen) < n_gp + 20:
            if len(survivors) < 2:
                break
            p_a = random.choice(survivors)
            p_b = random.choice(survivors)

            if random.random() < crossover_rate and p_a.formula != p_b.formula:
                child_formula = crossover_factor_formula(p_a.formula, p_b.formula)
                if child_formula:
                    next_gen.append(
                        FactorCandidate(
                            formula=child_formula,
                            template_name=f"gp_gen{gen}",
                            params={"source": "crossover"},
                        )
                    )
                    if len(next_gen) >= n_gp + 20:
                        break

            if random.random() < mutation_rate:
                target = random.choice(survivors)
                mutated = mutate_factor_formula(target.formula, mutation_strength=0.3)
                if mutated:
                    next_gen.append(
                        FactorCandidate(
                            formula=mutated,
                            template_name=f"gp_gen{gen}",
                            params={"source": "mutation"},
                        )
                    )

        gp_population = next_gen
        logger.debug("GP 第 %d 代完成：%d 个因子", gen + 1, len(gp_population))

    # 3. 合并并去重（基于公式自身）
    all_factors: dict[str, FactorCandidate] = {}
    for f in template_factors:
        if f.formula not in all_factors:
            all_factors[f.formula] = f
    for f in gp_population:
        if f.formula not in all_factors:
            all_factors[f.formula] = f

    merged = list(all_factors.values())
    logger.info(
        "因子池合并：模板 %d + GP %d = %d（去重后）",
        len(template_factors),
        len(gp_population),
        len(merged),
    )
    return merged


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
    use_gp: bool = False,
    n_gp: int = 80,
    gp_generations: int = 3,
) -> list[FactorCandidate]:
    """因子自动发现主流程。

    Args:
        db: 数据库会话。
        symbols: 品种代码列表（至少 1 个）。
        period: K 线周期。
        min_bars: 最少 K 线数。
        min_abs_rank_ic: Rank IC 过滤阈值。
        top_n: 最终保留因子数。
        use_gp: 是否启用 GP（遗传编程）生成额外因子。
        n_gp: GP 初始因子数量。
        gp_generations: GP 进化代数。

    Returns:
        Top-N 候选因子列表（已排序）。
    """
    if not symbols:
        raise ValueError("symbols 不能为空")

    logger.info("因子发现开始：symbols=%s，period=%s，use_gp=%s", symbols, period, use_gp)

    # 1. 模板生成
    candidates = generate_template_factors()
    if not candidates:
        logger.warning("模板生成返回空列表")
        return []

    # 1b. GP 生成（可选）
    if use_gp:
        logger.info("启用 GP 因子生成（n_gp=%d，gp_generations=%d）...", n_gp, gp_generations)
        candidates = evolve_factor_pool(
            template_factors=candidates,
            n_gp=n_gp,
            gp_generations=gp_generations,
        )

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
