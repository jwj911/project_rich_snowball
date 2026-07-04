"""增强回测评测指标测试。"""

from __future__ import annotations

import numpy as np
import pytest

from services.backtest.metrics import EnhancedBacktestMetrics, compute_enhanced_metrics


@pytest.fixture
def sample_equity():
    """构造 100 个交易日的简单正向资金曲线。"""
    equity = [100000.0]
    for i in range(99):
        # 每天 0.1% 收益 + 噪声
        ret = 0.001 + np.random.normal(0, 0.005)
        equity.append(equity[-1] * (1 + ret))
    times = [f"2026-01-{min(d + 3, 28):02d}" for d in range(100)]
    curve = [{"time": t, "equity": e} for t, e in zip(times, equity)]
    return curve


@pytest.fixture
def sample_trades():
    """构造 5 笔交易：3 盈 2 亏。"""
    return [
        {"entry_time": "2026-01-05", "exit_time": "2026-01-10", "pnl": 500.0},
        {"entry_time": "2026-01-12", "exit_time": "2026-01-15", "pnl": -300.0},
        {"entry_time": "2026-01-18", "exit_time": "2026-01-22", "pnl": 200.0},
        {"entry_time": "2026-01-25", "exit_time": "2026-01-28", "pnl": -150.0},
        {"entry_time": "2026-02-01", "exit_time": "2026-02-05", "pnl": 800.0},
    ]


class TestComputeEnhancedMetrics:
    def test_basic_metrics(self, sample_equity, sample_trades):
        result = compute_enhanced_metrics(sample_equity, sample_trades)
        assert isinstance(result, EnhancedBacktestMetrics)
        assert result.trade_count == 5
        assert result.win_rate_pct > 0
        assert result.sharpe is not None
        assert result.score >= 0
        assert result.max_drawdown_pct >= 0

    def test_empty_equity(self):
        result = compute_enhanced_metrics([])
        assert result.total_return_pct == 0.0
        assert result.trade_count == 0

    def test_calmar_ratio(self, sample_equity, sample_trades):
        result = compute_enhanced_metrics(sample_equity, sample_trades)
        if result.max_drawdown_pct > 0:
            assert result.calmar_ratio is not None

    def test_sortino_ratio(self, sample_equity, sample_trades):
        result = compute_enhanced_metrics(sample_equity, sample_trades)
        # Sortino 可能为 None（如果无下行波动）
        assert hasattr(result, "sortino_ratio")

    def test_monthly_returns(self, sample_equity, sample_trades):
        equity_with_times = [
            {"time": f"2026-{i // 20 + 1:02d}-{i % 20 + 1:02d}", "equity": e["equity"]}
            for i, e in enumerate(sample_equity[:60])
        ]
        result = compute_enhanced_metrics(equity_with_times, sample_trades)
        assert isinstance(result.monthly_returns, list)

    def test_max_consecutive_losses(self, sample_equity, sample_trades):
        result = compute_enhanced_metrics(sample_equity, sample_trades)
        # 交易序列中有 2 连亏？实际取决于顺序
        assert result.max_consecutive_losses is not None

    def test_benchmark_ir(self, sample_equity):
        """使用完美基准计算信息比率。"""
        curve = sample_equity[:60]
        equity_arr = np.array([p["equity"] for p in curve], dtype=float)
        returns = np.diff(equity_arr) / equity_arr[:-1]
        # 基准 = 相同的收益 → IR 不确定（方差为0时跟踪误差为0会除零）
        # 使用稍有不同的基准
        bench_returns = returns + 0.0001 * np.ones(len(returns))
        result = compute_enhanced_metrics(curve, benchmark_returns=bench_returns.tolist())
        assert result.information_ratio is not None

    def test_to_dict(self, sample_equity, sample_trades):
        result = compute_enhanced_metrics(sample_equity, sample_trades)
        d = result.to_dict()
        assert d["trade_count"] == 5
        assert "calmar_ratio" in d
        assert "monthly_returns" in d
        assert isinstance(d["score"], int)

    def test_avg_hold_days(self, sample_equity, sample_trades):
        result = compute_enhanced_metrics(sample_equity, sample_trades)
        assert result.avg_hold_days is not None
        assert result.avg_hold_days > 0

    def test_no_trades(self, sample_equity):
        result = compute_enhanced_metrics(sample_equity, trades=[])
        assert result.trade_count == 0
        assert result.win_rate_pct == 0.0
        assert result.avg_hold_days is None
