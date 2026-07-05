export interface BacktestTrade {
  entry_time: string
  exit_time: string
  direction: string
  entry_price: number
  exit_price: number
  quantity: number
  pnl: number
  return_pct: number
}

export interface BacktestEquityPoint {
  time: string
  equity: number
  pnl: number
  pnl_pct: number
}

export interface BacktestMetrics {
  score: number
  total_return_pct: number
  annualized_return_pct: number
  max_drawdown_pct: number
  win_rate_pct: number
  profit_factor: number
  sharpe: number
  trade_count: number
  total_fee?: number
}

export interface BacktestConfig {
  symbol: string
  period: string
  strategy_type: string
  short_window: number
  long_window: number
  initial_cash: number
  quantity: number
  multiplier: number
  fee_rate: number
  direction: string
  engine_mode?: string
  margin_rate?: number
  tick_size?: number
}

export interface BacktestResultData {
  config: BacktestConfig
  metrics: BacktestMetrics
  trades: BacktestTrade[]
  equity_curve: BacktestEquityPoint[]
  signals: Array<Record<string, unknown>>
  orders?: Array<Record<string, unknown>>
  contract?: Record<string, unknown>
  variety: Record<string, unknown>
  data_window: { start: string; end: string; bars: number }
}

export interface StrategyCondition {
  indicator: string
  operator: string
  indicator2?: string
  value?: number
}

export interface StrategyDSL {
  name: string
  description: string
  universe: string[]
  timeframe: string
  direction: string
  entry: { conditions: StrategyCondition[]; logic: string }
  exit: { conditions: StrategyCondition[]; logic: string }
  risk: {
    position_size: { type: string; value: number }
    stop_loss: { type: string; value: number }
    take_profit: { type: string; value: number }
  }
}

export interface StrategyCompilerData {
  dsl: StrategyDSL
  json: string
}
