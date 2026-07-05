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

## DSL Service Integration

`services.backtest.service.run_dsl_backtest()` now accepts an explicit
`engine_mode` argument:

- `engine_mode="legacy"`: default behavior, uses the original lightweight
  single-position engine.
- `engine_mode="futures"`: evaluates the same DSL entry/exit conditions, converts
  them into signed target lots, and runs the futures broker simulator.

The futures path reads contract settings from `VarietyDB`:

- `multiplier` -> contract multiplier;
- `tick_size` -> minimum price tick;
- `margin_rate` -> initial margin ratio;
- `commission` -> proportional commission rate when below `0.05`.

The returned payload keeps the familiar top-level fields (`config`, `metrics`,
`trades`, `equity_curve`, `signals`) and adds `contract` plus `orders` for
broker-level inspection.

Saved strategy backtests can pass the same mode through
`StrategyBacktestRequest.engine_mode`, currently typed as `"legacy" | "futures"`.

## Next Integration Steps

1. Feed `FuturesContractSpec` from extended contract settlement fields,
   preferring contract-specific long/short margin rates when available.
2. Add rollover-aware data loading for main/continuous contracts.
3. Add execution models for close-price execution, VWAP-like execution, and
   intraday order delay.
4. Persist or expose order/equity details in BacktestAgent responses and the
   frontend result card.
5. Decide whether BacktestAgent should default to `engine_mode="futures"` for all
   futures strategies after frontend display and metric wording are upgraded.
