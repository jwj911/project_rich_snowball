# Futures Backtest Framework Notes

## Reverse-Engineered Architecture

The referenced stock-selection framework is proprietary, so this project only
borrows architectural ideas, not implementation code.

Useful layers to keep:

1. Config layer: collect global account settings, strategy definitions, paths,
   and contract metadata into one immutable-ish object.
2. Data layer: normalize historical bars, precompute cacheable market panels,
   and keep data validation separate from simulation.
3. Factor/signal layer: compute indicators and strategy signals before trading
   simulation starts.
4. Target layer: convert signals into desired positions or target weights.
5. Broker/simulator layer: execute target changes bar by bar, apply market
   rules, fees, slippage, margin, and produce account snapshots.
6. Report layer: calculate metrics and expose trades, orders, and equity curve.

For futures, the broker/simulator layer is the first-class core. Stock-specific
ideas such as selected-stock pools, ST filters, limit-up/limit-down handling,
and financial factors are optional and should not leak into the futures engine.

## Implemented Foundation

`python/services/backtest/futures.py` adds a futures-specific broker simulator:

- signed target lots: positive long, negative short, zero flat;
- next-bar execution by default;
- contract multiplier, tick size, margin rate, commission rate, per-lot fee,
  and slippage ticks;
- long/short/flat transitions, including position flips;
- margin-based target clamping;
- maintenance-margin forced liquidation;
- order records, closed-trade records, and mark-to-market account snapshots;
- metrics for return, drawdown, Sharpe, win rate, profit factor, fees, and final
  equity.

The module is intentionally independent from the existing lightweight
`services.backtest.engine` so current BacktestAgent behavior remains stable.

## Next Integration Steps

1. Wire Strategy DSL conditions into `signals_to_target_lots()`, then run
   `run_futures_backtest()` in `services.backtest.service`.
2. Feed `FuturesContractSpec` from `VarietyDB` and extended contract margin
   fields, preferring contract-specific long/short margin rates when available.
3. Add rollover-aware data loading for main/continuous contracts.
4. Add execution models for close-price execution, VWAP-like execution, and
   intraday order delay.
5. Persist or expose order/equity details in BacktestAgent responses and the
   frontend result card.
