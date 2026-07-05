"""Backtesting framework for strategy agents."""

from services.backtest.futures import (
    FuturesBacktestConfig,
    FuturesBacktestResult,
    FuturesContractSpec,
    FuturesOrder,
    FuturesTrade,
    run_futures_backtest,
    signals_to_target_lots,
)
from services.backtest.metrics import EnhancedBacktestMetrics, compute_enhanced_metrics

__all__ = [
    "EnhancedBacktestMetrics",
    "FuturesBacktestConfig",
    "FuturesBacktestResult",
    "FuturesContractSpec",
    "FuturesOrder",
    "FuturesTrade",
    "compute_enhanced_metrics",
    "run_futures_backtest",
    "signals_to_target_lots",
]
