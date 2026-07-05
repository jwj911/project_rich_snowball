"""贝叶斯优化参数精调。

Phase 2B：使用 sklearn GaussianProcessRegressor + Expected Improvement
对 GA 产出的最优策略进行连续参数精调。

与网格搜索 (optimization_engine.py) 的区别：
- 网格搜索：暴力枚举，适合离散参数空间
- 贝叶斯优化：智能采样，适合连续参数空间，30-50 次迭代即可收敛
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel, Matern, WhiteKernel

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 可优化的参数定义
# ------------------------------------------------------------------

# 连续参数：(参数路径, 下限, 上限, 步长/精度)
CONTINUOUS_PARAMS: dict[str, tuple[float, float, float]] = {
    "stop_loss.atr_mult": (0.5, 5.0, 0.1),
    "take_profit.rr_ratio": (1.0, 5.0, 0.1),
    "position_size.pct": (0.05, 0.5, 0.01),
}

# 离散阈值参数：(参数路径, 候选值)
THRESHOLD_VALUES: dict[str, list[float]] = {
    "entry_threshold_0": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95],
    "entry_threshold_1": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95],
    "entry_threshold_2": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95],
}


@dataclass
class BOParams:
    """贝叶斯优化参数向量。

    用于将连续参数编码为 [0,1] 归一化向量，方便 GP 建模。
    """

    stop_loss_atr: float = 2.0
    take_profit_rr: float = 2.0
    position_size_pct: float = 0.2

    # 入场条件的阈值（最多 3 个）
    thresholds: list[float] = field(default_factory=lambda: [0.5])

    def to_normalized(self) -> np.ndarray:
        """转换为 [0,1] 归一化向量。（5 维：3 个连续 + 2 个填充）"""
        return np.array(
            [
                (self.stop_loss_atr - 0.5) / 4.5,
                (self.take_profit_rr - 1.0) / 4.0,
                (self.position_size_pct - 0.05) / 0.45,
                self.thresholds[0] if len(self.thresholds) > 0 else 0.5,
                self.thresholds[1] / 0.95 if len(self.thresholds) > 1 else 0.5,
            ],
            dtype=np.float64,
        )

    @classmethod
    def from_normalized(cls, x: np.ndarray, n_thresholds: int = 1) -> BOParams:
        """从归一化向量恢复。"""
        params = cls()
        params.stop_loss_atr = round(x[0] * 4.5 + 0.5, 1)
        params.take_profit_rr = round(x[1] * 4.0 + 1.0, 1)
        params.position_size_pct = round(x[2] * 0.45 + 0.05, 2)
        params.thresholds = [round(x[3], 2)]
        if n_thresholds > 1:
            params.thresholds.append(round(x[4], 2))
        return params

    def clamp(self) -> BOParams:
        """确保所有参数在合法范围内。"""
        self.stop_loss_atr = max(0.5, min(5.0, self.stop_loss_atr))
        self.take_profit_rr = max(1.0, min(5.0, self.take_profit_rr))
        self.position_size_pct = max(0.05, min(0.5, self.position_size_pct))
        self.thresholds = [max(0.05, min(0.99, t)) for t in self.thresholds]
        return self


def _expected_improvement(
    x: np.ndarray,
    gp: GaussianProcessRegressor,
    y_best: float,
    xi: float = 0.01,
) -> float:
    """Expected Improvement (EI) 采集函数。

    EI(x) = (mu - y_best - xi) * Phi(Z) + sigma * phi(Z)
    其中 Z = (mu - y_best - xi) / sigma

    Args:
        x: 候选点 (1, n_features)。
        gp: 已拟合的 GP 模型。
        y_best: 当前最优观测值。
        xi: 探索-利用平衡参数（>0 鼓励探索）。

    Returns:
        EI 值。
    """
    mu, sigma = gp.predict(x, return_std=True)
    mu = mu[0]
    sigma = sigma[0]

    if sigma < 1e-9:
        return 0.0

    from scipy.stats import norm

    improvement = mu - y_best - xi
    z_score = improvement / sigma

    ei = improvement * norm.cdf(z_score) + sigma * norm.pdf(z_score)
    return float(max(0.0, ei))


def _random_sample(n_dim: int = 5) -> np.ndarray:
    """在 [0,1]^n_dim 空间内随机采样。"""
    return np.random.default_rng().random(n_dim)


def _random_search_max(
    objective_fn,
    bounds: list[tuple[float, float]],
    n_samples: int = 200,
) -> tuple[np.ndarray, float]:
    """随机搜索最优值，用于初始化 BO。

    Args:
        objective_fn: 目标函数 f(x) -> float（最大化）。
        bounds: 每个维度的 (lower, upper)。
        n_samples: 采样数量。

    Returns:
        (最优参数向量, 最优目标值)。
    """
    best_x = None
    best_y = float("-inf")

    for _ in range(n_samples):
        x = np.array([np.random.uniform(low, high) for low, high in bounds])
        try:
            y = objective_fn(x)
        except Exception:
            continue
        if y > best_y:
            best_y = y
            best_x = x

    return best_x, best_y


class BayesianOptimizer:
    """贝叶斯优化器。

    使用 GP 模型对适应度函数的参数空间进行建模，
    通过 Expected Improvement 采集函数指导搜索。
    """

    def __init__(
        self,
        n_dim: int = 5,
        n_initial: int = 10,
        n_iterations: int = 30,
        exploration_xi: float = 0.01,
        random_state: int | None = 42,
    ):
        self.n_dim = n_dim
        self.n_initial = n_initial
        self.n_iterations = n_iterations
        self.exploration_xi = exploration_xi

        # GP 核：RBF(平滑) + Matern(局部变化) + WhiteKernel(噪声)
        kernel = (
            (
                ConstantKernel(1.0, constant_value_bounds=(1e-3, 1e3))
                * RBF(length_scale=1.0, length_scale_bounds=(1e-2, 1e2))
            )
            + Matern(length_scale=1.0, length_scale_bounds=(1e-2, 1e2), nu=2.5)
            + WhiteKernel(noise_level=1e-3, noise_level_bounds=(1e-5, 1e-1))
        )

        self.gp = GaussianProcessRegressor(
            kernel=kernel,
            n_restarts_optimizer=5,
            random_state=random_state,
            alpha=1e-6,
            normalize_y=True,
        )

        # 观测历史
        self.X_observed: list[np.ndarray] = []
        self.y_observed: list[float] = []

    def _initial_sampling(self, objective_fn) -> None:
        """拉丁超立方初始化采样。"""
        # 简化版 LHS：分层随机采样
        for i in range(self.n_initial):
            # 分层采样确保覆盖空间
            x = np.array([(np.random.random() + i) / self.n_initial % 1.0 for _ in range(self.n_dim)])
            try:
                y = objective_fn(x)
            except Exception as exc:
                logger.debug("BO 初始采样 %d 失败：%s", i, exc)
                continue
            self.X_observed.append(x)
            self.y_observed.append(y)

        if not self.X_observed:
            raise RuntimeError("BO 初始采样全部失败，无法继续优化")

        logger.info(
            "BO 初始采样完成：%d/%d 成功，最优 y=%.4f",
            len(self.X_observed),
            self.n_initial,
            max(self.y_observed),
        )

    def optimize(self, objective_fn) -> tuple[np.ndarray, float, list[dict[str, Any]]]:
        """运行贝叶斯优化。

        Args:
            objective_fn: 目标函数 f(normalized_x: np.ndarray) -> float（最大化）。

        Returns:
            (最优参数向量, 最优目标值, 迭代历史)。
        """
        history: list[dict[str, Any]] = []

        # 初始采样
        try:
            self._initial_sampling(objective_fn)
        except RuntimeError:
            return np.zeros(self.n_dim), 0.0, history

        best_idx = int(np.argmax(self.y_observed))
        best_x = self.X_observed[best_idx].copy()
        best_y = self.y_observed[best_idx]

        history.append(
            {
                "iteration": 0,
                "best_y": float(best_y),
                "n_observed": len(self.X_observed),
                "phase": "initial",
            }
        )

        # 迭代优化
        for it in range(self.n_iterations):
            x_arr = np.array(self.X_observed)
            y_arr = np.array(self.y_observed)

            # 拟合 GP
            try:
                self.gp.fit(x_arr, y_arr)
            except Exception as exc:
                logger.warning("BO 第 %d 轮 GP 拟合失败：%s", it + 1, exc)
                history.append(
                    {
                        "iteration": it + 1,
                        "best_y": float(best_y),
                        "error": str(exc),
                    }
                )
                continue

            # 优化 EI 采集函数：在随机候选点中选 EI 最高者
            n_candidates = 500
            candidates = np.random.default_rng().random((n_candidates, self.n_dim))
            ei_values = np.array(
                [_expected_improvement(c.reshape(1, -1), self.gp, best_y, self.exploration_xi) for c in candidates]
            )
            next_x = candidates[int(np.argmax(ei_values))]

            # 评估
            try:
                next_y = objective_fn(next_x)
            except Exception as exc:
                logger.debug("BO 第 %d 轮评估失败：%s", it + 1, exc)
                history.append(
                    {
                        "iteration": it + 1,
                        "best_y": float(best_y),
                        "error": str(exc),
                    }
                )
                continue

            self.X_observed.append(next_x)
            self.y_observed.append(next_y)

            if next_y > best_y:
                best_y = next_y
                best_x = next_x.copy()

            history.append(
                {
                    "iteration": it + 1,
                    "best_y": float(best_y),
                    "current_y": float(next_y),
                    "ei_max": float(ei_values.max()),
                    "n_observed": len(self.X_observed),
                }
            )

            if (it + 1) % 10 == 0:
                logger.info(
                    "BO 迭代 %d/%d：最优 y=%.4f，观测 %d 个点",
                    it + 1,
                    self.n_iterations,
                    best_y,
                    len(self.X_observed),
                )

        logger.info("BO 完成：最优 y=%.4f（%d 次迭代，%d 个观测）", best_y, self.n_iterations, len(self.X_observed))
        return best_x, best_y, history


def optimize_strategy_params_bayesian(
    backtest_fn,
    initial_params: dict[str, Any],
    n_iterations: int = 30,
    n_initial: int = 10,
    random_state: int | None = 42,
) -> tuple[dict[str, Any], float, list[dict[str, Any]]]:
    """策略参数的贝叶斯优化。

    这是高级封装，接受回测函数和初始参数，返回最优参数。

    Args:
        backtest_fn: callable(params: dict) -> float，接收参数字典，返回适应度分数。
        initial_params: 初始参数字典，包含 stop_loss_atr, take_profit_rr, position_size_pct, thresholds。
        n_iterations: BO 迭代次数。
        n_initial: 初始随机采样数量。
        random_state: 随机种子。

    Returns:
        (最优参数字典, 最优适应度, 优化历史)。
    """
    bo = BayesianOptimizer(
        n_dim=5,
        n_initial=n_initial,
        n_iterations=n_iterations,
        random_state=random_state,
    )

    # 将 initial_params 转换为归一化向量作为初始点
    init = BOParams(
        stop_loss_atr=float(initial_params.get("stop_loss_atr", 2.0)),
        take_profit_rr=float(initial_params.get("take_profit_rr", 2.0)),
        position_size_pct=float(initial_params.get("position_size_pct", 0.2)),
        thresholds=list(initial_params.get("thresholds", [0.5])),
    )

    n_thresholds = len(init.thresholds)

    def objective(normalized_x: np.ndarray) -> float:
        params = BOParams.from_normalized(normalized_x, n_thresholds=n_thresholds)
        params.clamp()

        param_dict = {
            "stop_loss_atr": params.stop_loss_atr,
            "take_profit_rr": params.take_profit_rr,
            "position_size_pct": params.position_size_pct,
            "thresholds": params.thresholds,
        }

        return float(backtest_fn(param_dict))

    # 注入初始点
    best_x, best_y, history = bo.optimize(objective)

    best_params = BOParams.from_normalized(best_x, n_thresholds=n_thresholds)
    best_params.clamp()

    result_dict = {
        "stop_loss_atr": best_params.stop_loss_atr,
        "take_profit_rr": best_params.take_profit_rr,
        "position_size_pct": best_params.position_size_pct,
        "thresholds": best_params.thresholds,
    }

    return result_dict, best_y, history


__all__ = [
    "BayesianOptimizer",
    "BOParams",
    "optimize_strategy_params_bayesian",
    "_expected_improvement",
]
