"""策略生命周期管理。

跟踪进化生成策略和人工策略的表现，检测退化趋势，推荐行动。
"""

from __future__ import annotations

import contextlib
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

logger = logging.getLogger("agent.evolution.lifecycle")

# 退化评分阈值
DECAY_THRESHOLD_KEEP = 20
DECAY_THRESHOLD_PAPER = 40
DECAY_THRESHOLD_REOPTIMIZE = 70


class StrategyLifecycleManager:
    """策略生命周期管理器。

    功能：
    - 注册新策略（进化生成或人工创建）
    - 定期评估策略退化程度
    - 推荐行动（保持 / 模拟跟踪 / 重新优化 / 退役）

    所有方法接受 Session 作为第一个参数，遵循项目服务层模式。
    """

    # ------------------------------------------------------------------
    # 注册
    # ------------------------------------------------------------------

    @staticmethod
    def register_strategy(
        db: Session,
        strategy_id: int,
        source: str = "manual",
        evolution_run_id: int | None = None,
        is_metrics: dict[str, Any] | None = None,
        oos_metrics: dict[str, Any] | None = None,
    ) -> None:
        """注册策略生命周期记录。

        Args:
            db: 数据库 session。
            strategy_id: 策略 ID。
            source: 来源（"manual" 或 "evolved"）。
            evolution_run_id: 关联的进化运行 ID（仅 evolved 来源）。
            is_metrics: 样本内回测指标 dict（可选）。
            oos_metrics: 样本外回测指标 dict（可选）。
        """
        from models import StrategyLifecycleDB

        existing = db.query(StrategyLifecycleDB).filter(StrategyLifecycleDB.strategy_id == strategy_id).first()
        if existing:
            logger.info("策略 %d 已有生命周期记录，跳过注册。", strategy_id)
            return

        lifecycle = StrategyLifecycleDB(
            strategy_id=strategy_id,
            source=source,
            evolution_run_id=evolution_run_id,
            status="active",
            in_sample_metrics=json.dumps(is_metrics, ensure_ascii=False) if is_metrics else None,
            out_of_sample_metrics=json.dumps(oos_metrics, ensure_ascii=False) if oos_metrics else None,
            last_evaluated_at=datetime.now(UTC),
            decay_score=0,
        )
        db.add(lifecycle)
        db.commit()
        logger.info("策略 %d 生命周期已注册（来源=%s）。", strategy_id, source)

    # ------------------------------------------------------------------
    # 衰减评估
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate_decay(
        db: Session,
        strategy_id: int,
        recent_metrics: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """评估策略退化程度。

        比较最近表现与历史回测基准，计算 decay_score (0-100)。
        score 越高表示退化越严重。

        Args:
            db: 数据库 session。
            strategy_id: 策略 ID。
            recent_metrics: 最近回测指标 dict（包含 sharpe, profit_factor, win_rate, trade_count）。
                           如果为 None，则从最新 BacktestRunDB 中获取。

        Returns:
            dict: {
                "decay_score": float (0-100),
                "status": str (active/paper_trading/degraded/retired),
                "recommended_action": str (keep/paper_trade/re_optimize/retire),
                "details": dict (各维度得分),
            }
        """
        from models import StrategyLifecycleDB

        lifecycle = db.query(StrategyLifecycleDB).filter(StrategyLifecycleDB.strategy_id == strategy_id).first()

        if lifecycle is None:
            return {
                "decay_score": 0,
                "status": "active",
                "recommended_action": "keep",
                "details": {"error": "无生命周期记录"},
            }

        # 获取基准指标（注册时保存的 IS 指标）
        baseline = {}
        if lifecycle.in_sample_metrics:
            try:
                baseline = json.loads(lifecycle.in_sample_metrics)
            except (json.JSONDecodeError, TypeError):
                baseline = {}

        # 获取最近指标
        if recent_metrics is None:
            recent_metrics = _get_latest_backtest_metrics(db, strategy_id)

        if not recent_metrics or not baseline:
            # 没有足够数据，默认健康
            lifecycle.decay_score = 0
            lifecycle.last_evaluated_at = datetime.now(UTC)
            db.commit()
            return {
                "decay_score": 0,
                "status": lifecycle.status,
                "recommended_action": "keep",
                "details": {"note": "数据不足，无法评估衰减"},
            }

        # 计算各维度退化分数（每个 0-100）
        components: dict[str, float] = {}

        # 1. Sharpe 比率退化
        is_sharpe = float(baseline.get("sharpe", 0) or 0)
        recent_sharpe = float(recent_metrics.get("sharpe", 0) or 0)
        components["sharpe_deterioration"] = _sharpe_decay(is_sharpe, recent_sharpe)

        # 2. 盈亏比退化
        is_pf = float(baseline.get("profit_factor", 0) or 0)
        recent_pf = float(recent_metrics.get("profit_factor", 0) or 0)
        components["profit_factor_deterioration"] = _ratio_decay(is_pf, recent_pf)

        # 3. 胜率退化
        is_wr = float(baseline.get("win_rate", 0) or 0)
        recent_wr = float(recent_metrics.get("win_rate", 0) or 0)
        components["win_rate_deterioration"] = _win_rate_decay(is_wr, recent_wr)

        # 4. 交易频率退化
        is_tc = int(baseline.get("trade_count", 0) or 0)
        recent_tc = int(recent_metrics.get("trade_count", 0) or 0)
        components["trade_frequency_deterioration"] = _trade_count_decay(is_tc, recent_tc)

        # 综合衰减分（加权平均）
        weights = {
            "sharpe_deterioration": 0.40,
            "profit_factor_deterioration": 0.25,
            "win_rate_deterioration": 0.15,
            "trade_frequency_deterioration": 0.20,
        }
        decay_score = sum(components[k] * weights[k] for k in weights)

        # 更新记录
        lifecycle.decay_score = round(float(decay_score), 2)
        lifecycle.last_evaluated_at = datetime.now(UTC)

        # 根据衰减分推荐状态
        new_status, action = _score_to_action(decay_score)
        if lifecycle.status not in ("retired",):
            lifecycle.status = new_status
        lifecycle.updated_at = datetime.now(UTC)
        db.commit()

        return {
            "decay_score": round(float(decay_score), 2),
            "status": lifecycle.status,
            "recommended_action": action,
            "details": components,
        }

    @staticmethod
    def detect_decay(
        db: Session,
        strategy_id: int,
    ) -> dict[str, Any]:
        """详细衰减检测（基于回测历史）。

        分析策略随时间推移的表现趋势。

        Returns:
            dict: {
                "signal_frequency_decline": bool,
                "rolling_sharpe_declining": bool,
                "profit_factor_declining": bool,
                "decay_signals": list[str],
                "decay_score": float,
            }
        """
        from models import BacktestRunDB

        runs = (
            db.query(BacktestRunDB)
            .filter(
                BacktestRunDB.strategy_id == strategy_id,
                BacktestRunDB.status == "completed",
            )
            .order_by(BacktestRunDB.created_at.asc())
            .all()
        )

        if len(runs) < 2:
            return {
                "signal_frequency_decline": False,
                "rolling_sharpe_declining": False,
                "profit_factor_declining": False,
                "decay_signals": [],
                "decay_score": 0,
                "note": "回测记录不足（需 ≥2 次）",
            }

        decay_signals: list[str] = []
        details: dict[str, Any] = {}

        # 提取指标序列
        metrics_seq = []
        for run in runs:
            try:
                if run.result_json:
                    result = json.loads(run.result_json)
                    m = result.get("metrics", {})
                    metrics_seq.append(
                        {
                            "sharpe": float(m.get("sharpe", 0) or 0),
                            "profit_factor": float(m.get("profit_factor", 0) or 0),
                            "win_rate": float(m.get("win_rate", 0) or 0),
                            "trade_count": int(m.get("trade_count", 0) or 0),
                        }
                    )
            except (json.JSONDecodeError, TypeError, KeyError):
                continue

        if len(metrics_seq) < 2:
            return {
                "decay_signals": [],
                "decay_score": 0,
                "note": "可解析指标不足",
            }

        # 检测信号
        first = metrics_seq[0]
        last = metrics_seq[-1]

        # 1. 信号频率下降 > 50%
        if first.get("trade_count", 1) > 0:
            freq_ratio = last.get("trade_count", 0) / first.get("trade_count", 1)
        else:
            freq_ratio = 1.0
        details["trade_count_ratio"] = round(freq_ratio, 3)
        if freq_ratio < 0.5:
            decay_signals.append("信号频率显著下降")
            details["signal_frequency_decline"] = True
        else:
            details["signal_frequency_decline"] = False

        # 2. 滚动 Sharpe 趋势
        sharpes = [m["sharpe"] for m in metrics_seq]
        if len(sharpes) >= 3:
            slope = _linear_trend_slope(sharpes)
            details["sharpe_trend_slope"] = round(slope, 4)
            if slope < -0.01 and sharpes[-1] < 0:
                decay_signals.append("滚动 Sharpe 持续为负")
                details["rolling_sharpe_declining"] = True
            else:
                details["rolling_sharpe_declining"] = False
        else:
            details["rolling_sharpe_declining"] = False

        # 3. 盈亏比恶化 > 30%
        if first.get("profit_factor", 1) > 0:
            pf_ratio = last.get("profit_factor", 0) / first.get("profit_factor", 1)
        else:
            pf_ratio = 1.0
        details["profit_factor_ratio"] = round(pf_ratio, 3)
        if pf_ratio < 0.7:
            decay_signals.append("盈亏比显著恶化")
            details["profit_factor_declining"] = True
        else:
            details["profit_factor_declining"] = False

        decay_score = len(decay_signals) / 3 * 100  # 0, 33.3, 66.7, 100

        return {
            "signal_frequency_decline": details.get("signal_frequency_decline", False),
            "rolling_sharpe_declining": details.get("rolling_sharpe_declining", False),
            "profit_factor_declining": details.get("profit_factor_declining", False),
            "decay_signals": decay_signals,
            "decay_score": round(decay_score, 1),
            "details": details,
        }

    # ------------------------------------------------------------------
    # 行动推荐
    # ------------------------------------------------------------------

    @staticmethod
    def recommend_action(db: Session, strategy_id: int) -> str:
        """基于当前衰减分数推荐行动。

        Returns:
            "keep" | "paper_trade" | "re_optimize" | "retire"
        """
        from models import StrategyLifecycleDB

        lifecycle = db.query(StrategyLifecycleDB).filter(StrategyLifecycleDB.strategy_id == strategy_id).first()

        if lifecycle is None or lifecycle.decay_score is None:
            return "keep"

        return _decay_to_action(float(lifecycle.decay_score))

    # ------------------------------------------------------------------
    # 策略对比
    # ------------------------------------------------------------------

    @staticmethod
    def compare_strategies(
        db: Session,
        strategy_ids: list[int],
    ) -> list[dict[str, Any]]:
        """多策略对比，按综合质量排名。

        Returns:
            按 (decay_score asc, 历史表现 desc) 排序的策略列表。
        """
        from models import StrategyDB, StrategyLifecycleDB

        results = []
        for sid in strategy_ids:
            lifecycle = db.query(StrategyLifecycleDB).filter(StrategyLifecycleDB.strategy_id == sid).first()

            strategy = db.query(StrategyDB).filter(StrategyDB.id == sid).first()

            entry = {
                "strategy_id": sid,
                "strategy_name": strategy.name if strategy else "—",
                "symbol": strategy.symbol if strategy else "—",
                "has_lifecycle": lifecycle is not None,
                "status": lifecycle.status if lifecycle else "unknown",
                "decay_score": float(lifecycle.decay_score) if lifecycle and lifecycle.decay_score else None,
                "source": lifecycle.source if lifecycle else "unknown",
                "recommended_action": (
                    _decay_to_action(float(lifecycle.decay_score)) if lifecycle and lifecycle.decay_score else "keep"
                ),
            }
            results.append(entry)

        # 排序：衰减分低 → 高，nil 排最后
        results.sort(
            key=lambda r: (
                0 if r["decay_score"] is not None else 1,
                r["decay_score"] if r["decay_score"] is not None else 100,
            )
        )
        return results

    # ------------------------------------------------------------------
    # 摘要
    # ------------------------------------------------------------------

    @staticmethod
    def get_lifecycle_summary(db: Session, strategy_id: int) -> dict[str, Any]:
        """获取策略生命周期的结构化摘要（供前端使用）。"""
        from models import StrategyDB, StrategyLifecycleDB

        lifecycle = db.query(StrategyLifecycleDB).filter(StrategyLifecycleDB.strategy_id == strategy_id).first()
        strategy = db.query(StrategyDB).filter(StrategyDB.id == strategy_id).first()

        if lifecycle is None:
            return {
                "strategy_id": strategy_id,
                "strategy_name": strategy.name if strategy else "—",
                "has_lifecycle": False,
            }

        is_metrics = None
        oos_metrics = None
        with contextlib.suppress(json.JSONDecodeError, TypeError):
            if lifecycle.in_sample_metrics:
                is_metrics = json.loads(lifecycle.in_sample_metrics)
            if lifecycle.out_of_sample_metrics:
                oos_metrics = json.loads(lifecycle.out_of_sample_metrics)

        return {
            "strategy_id": strategy_id,
            "strategy_name": strategy.name if strategy else "—",
            "has_lifecycle": True,
            "source": lifecycle.source,
            "status": lifecycle.status,
            "evolution_run_id": lifecycle.evolution_run_id,
            "in_sample_metrics": is_metrics,
            "out_of_sample_metrics": oos_metrics,
            "decay_score": float(lifecycle.decay_score) if lifecycle.decay_score else None,
            "performance_trend": float(lifecycle.performance_trend) if lifecycle.performance_trend else None,
            "last_evaluated_at": lifecycle.last_evaluated_at.isoformat() if lifecycle.last_evaluated_at else None,
            "recommended_action": (_decay_to_action(float(lifecycle.decay_score)) if lifecycle.decay_score else "keep"),
        }


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------


def _score_to_action(decay_score: float) -> tuple[str, str]:
    """根据衰减分返回 (状态, 推荐行动)。"""
    if decay_score < DECAY_THRESHOLD_KEEP:
        return "active", "keep"
    elif decay_score < DECAY_THRESHOLD_PAPER:
        return "paper_trading", "paper_trade"
    elif decay_score < DECAY_THRESHOLD_REOPTIMIZE:
        return "degraded", "re_optimize"
    else:
        return "retired", "retire"


def _decay_to_action(decay_score: float) -> str:
    """衰减分 → 行动字符串。"""
    return _score_to_action(decay_score)[1]


def _sharpe_decay(is_sharpe: float, recent_sharpe: float) -> float:
    """计算 Sharpe 比率退化分数 (0-100)。"""
    if abs(is_sharpe) < 0.01:
        return 100.0 if recent_sharpe < -0.1 else 0.0
    drop = (is_sharpe - recent_sharpe) / abs(is_sharpe)
    # drop > 0 → 退化；drop < 0 → 改善
    return max(0.0, min(100.0, drop * 100.0))


def _ratio_decay(is_val: float, recent_val: float) -> float:
    """计算比率退化分数（通用，用于盈亏比等）。"""
    if abs(is_val) < 0.01:
        return 100.0 if recent_val < 0.5 else 0.0
    ratio = recent_val / is_val
    # ratio < 1 → 退化
    if ratio >= 1.0:
        return 0.0
    return max(0.0, min(100.0, (1.0 - ratio) * 100.0))


def _win_rate_decay(is_wr: float, recent_wr: float) -> float:
    """计算胜率退化分数。"""
    drop = is_wr - recent_wr  # 绝对下降
    if drop <= 0:
        return 0.0
    # 胜率下降 20% → 100
    return max(0.0, min(100.0, drop * 100.0 / 0.20))


def _trade_count_decay(is_count: int, recent_count: int) -> float:
    """计算交易频率退化分数。"""
    if is_count <= 0:
        return 0.0
    ratio = recent_count / is_count
    if ratio >= 1.0:
        return 0.0
    return max(0.0, min(100.0, (1.0 - ratio) * 100.0))


def _linear_trend_slope(values: list[float]) -> float:
    """简单线性趋势斜率（最小二乘法）。"""
    n = len(values)
    if n < 2:
        return 0.0
    x_mean = (n - 1) / 2.0
    y_mean = sum(values) / n
    numerator = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    denominator = sum((i - x_mean) ** 2 for i in range(n))
    if abs(denominator) < 1e-9:
        return 0.0
    return numerator / denominator


def _get_latest_backtest_metrics(
    db: Session,
    strategy_id: int,
) -> dict[str, Any] | None:
    """获取策略最新的回测指标。"""
    from models import BacktestRunDB

    run = (
        db.query(BacktestRunDB)
        .filter(
            BacktestRunDB.strategy_id == strategy_id,
            BacktestRunDB.status == "completed",
        )
        .order_by(BacktestRunDB.created_at.desc())
        .first()
    )

    if run is None or run.result_json is None:
        return None

    try:
        result = json.loads(run.result_json)
        return result.get("metrics", {})
    except (json.JSONDecodeError, TypeError):
        return None
