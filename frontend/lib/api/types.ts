export interface Product {
  id: number
  name: string
  symbol: string
  current_price: number | null
  change_percent: number | null | undefined
  open_price: number | null
  high: number | null
  low: number | null
  close_price: number | null
  settle: number | null
  volume: number | null
  pre_settlement: number | null
  open_interest: number | null
  oi_chg: number | null
  bid1: number | null
  ask1: number | null
  category: string | null
  margin: number | null
  commission: number | null
  updated_at: string
  trade_date: string | null
  limit_up: number | null
  limit_down: number | null
  price_precision: number
  margin_rate?: number | null
  contract_code?: string
  exchange?: string
  tick_size?: number | null
}

export interface ProductQuery {
  skip?: number
  limit?: number
  search?: string
  category?: string
  direction?: 'all' | 'up' | 'down'
  sortBy?: 'change_percent' | 'volume' | 'current_price'
  sortOrder?: 'asc' | 'desc'
}

export interface ProductListResponse {
  items: Product[]
  total: number
  totalVolume: number
  upCount: number
  downCount: number
  categories: string[]
}

export interface Comment {
  id: number
  product_symbol: string | null
  product_name: string | null
  variety_id: number | null
  variety_symbol: string | null
  variety_name: string | null
  user_id: number
  username: string
  content: string
  sentiment: 'bullish' | 'bearish' | 'neutral' | null
  price_level_id: number | null
  created_at: string
}

export interface ProductDetail {
  product: Product
  comments: Comment[]
}

export interface User {
  id: number
  username: string
  email: string
  created_at: string
}

export interface RealtimeQuote {
  symbol: string
  current_price: number
  change_percent: number
  open_price: number | null
  high: number | null
  low: number | null
  volume: number | null
  open_interest: number | null
  pre_settlement: number | null
  updated_at: string
  limit_up: number | null
  limit_down: number | null
}

export interface KlineData {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  contract_code?: string | null
  contract_id?: number | null
}

export interface Variety {
  id: number
  symbol: string
  contract_code: string
  name: string
  exchange: string
  category: string | null
  margin_rate: number | null
  commission: number | null
  tick_size: number | null
  price_precision: number
}

export interface FutContract {
  id: number
  ts_code: string
  symbol: string | null
  name: string | null
  fut_code: string | null
  exchange: string | null
  list_date: string | null
  delist_date: string | null
  contract_type: string | null
  is_active: boolean
}

export interface ContractRollover {
  id: number
  variety_id: number
  old_contract_id: number | null
  new_contract_id: number | null
  old_contract_code: string | null
  new_contract_code: string | null
  effective_date: string
  source: string
  created_at: string
}

export type PriceLevelScope = 'continuous' | 'main' | 'contract'

export interface PriceLevel {
  id: number
  user_id: number
  variety_id: number
  contract_id: number | null
  variety_symbol: string | null
  variety_name: string | null
  type: 'support' | 'resistance'
  price: string
  scope: PriceLevelScope
  note: string | null
  source: string
  created_at: string
  updated_at: string
}

export interface Watchlist {
  id: number
  user_id: number
  variety_id: number
  variety_symbol: string
  variety_name: string
  notes: string | null
  is_notified: boolean
  created_at: string
}

export interface WorkspaceSummary {
  price_levels: PriceLevel[]
  watchlists: Watchlist[]
  recent_comments: Comment[]
}

export interface TokenResponse {
  access_token: string
  token_type: string
  refresh_token?: string | null
  expires_in: number
}

export interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
}

export interface VarietyFees {
  symbol: string
  name: string | null
  exchange: string | null
  margin_rate: number | null
  margin_amount: number | null
  commission_open: number | null
  commission_close: number | null
  commission_close_today: number | null
  unit: string | null
  updated_at: string | null
}

export interface MarketStatusResponse {
  date: string
  is_trading_day: boolean
  current_session: string
  next_trade_date: string | null
  remark: string | null
}

export interface UserPreference {
  user_id: number
  theme: 'dark' | 'light' | 'system'
  polling_interval_seconds: number
  notifications_enabled: boolean
  language: string
  created_at: string | null
  updated_at: string | null
}

export interface UserPreferenceUpdate {
  theme?: 'dark' | 'light' | 'system' | null
  polling_interval_seconds?: number | null
  notifications_enabled?: boolean | null
  language?: string | null
}

export interface LLMConfigResponse {
  provider: string
  base_url: string
  model: string
  has_api_key: boolean
  api_key_masked: string | null
  uses_system_default: boolean
  updated_at: string | null
}

export interface LLMConfigUpdate {
  provider: string
  base_url: string
  model: string
  api_key?: string | null
}

export interface LLMConfigTestResponse {
  ok: boolean
  model: string
  message: string
}

export interface NewsSource {
  id: number
  name: string
  url: string
  category: string | null
  is_enabled: boolean
  is_builtin: boolean
  user_id: number | null
  last_fetched_at: string | null
  fetch_error_count: number
  created_at: string
}

export interface NewsArticle {
  id: number
  source_id: number
  title: string
  summary: string | null
  ai_summary: string | null
  url: string
  published_at: string | null
  fetched_at: string
  alert_event_id?: number | null
  alert_severity?: 'low' | 'medium' | 'high' | 'critical' | null
}

export interface DailyCount {
  date: string
  count: number
}

export interface DashboardOverview {
  users: {
    total: number
    today: number
    this_week: number
  }
  comments: {
    total: number
    today: number
  }
  engagement: {
    price_levels: number
    watchlists: number
  }
  market: {
    total_varieties: number
    active_varieties: number
  }
  timestamp: string
}

export interface DashboardActivity {
  new_users: DailyCount[]
  comments: DailyCount[]
  since: string
  timestamp: string
}

export interface CollectionRun {
  job_name: string
  source: string
  status: string
  started_at: string | null
  duration_ms: number | null
  success_count: number | null
  failed_count: number | null
}

export interface DashboardCollection {
  last_24h: {
    total: number
    success: number
    failed: number
    success_rate: number | null
    avg_duration_ms: number | null
  }
  recent_runs: CollectionRun[]
  circuit_breakers: Record<string, unknown>
  timestamp: string
}


export interface Opinion {
  id: number
  user_id: number
  variety_id: number
  variety_symbol: string
  variety_name: string
  type: 'long' | 'short' | 'neutral'
  reason: string | null
  target_price: string | null
  stop_loss: string | null
  status: 'open' | 'closed_profit' | 'closed_loss' | 'expired'
  actual_outcome: 'profit' | 'loss' | 'breakeven' | null
  created_at: string
  closed_at: string | null
}

export interface OpinionCreate {
  variety_id: number
  type: 'long' | 'short' | 'neutral'
  reason: string
  target_price?: string | null
  stop_loss?: string | null
}

export interface OpinionUpdate {
  reason?: string | null
  target_price?: string | null
  stop_loss?: string | null
  status?: 'open' | 'closed_profit' | 'closed_loss' | 'expired' | null
  actual_outcome?: 'profit' | 'loss' | 'breakeven' | null
}


export interface PriceAlert {
  id: number
  user_id: number
  variety_id: number
  variety_symbol: string
  variety_name: string
  alert_type: 'above' | 'below'
  target_price: string
  is_triggered: boolean
  triggered_at: string | null
  created_at: string
}

export interface PriceAlertCreate {
  variety_id: number
  alert_type: 'above' | 'below'
  target_price: string
}

export interface PriceAlertUpdate {
  target_price?: string | null
  is_triggered?: boolean | null
}

export type AlertCategory = 'news' | 'market' | 'calendar'
export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical'

export interface AlertEvent {
  id: number
  category: AlertCategory
  severity: AlertSeverity
  title: string
  summary: string | null
  source_type: string
  source_id: number | null
  source_url: string | null
  related_variety_id: number | null
  related_variety_symbol: string | null
  related_variety_name: string | null
  user_id: number | null
  target_scope: 'personal' | 'broadcast'
  triggered_at: string
  created_at: string
  read_at: string | null
  dismissed_at: string | null
}

export interface AlertSummary {
  unread_count: number
  news_count: number
  market_count: number
}

export interface AlertEventQuery {
  category?: AlertCategory
  severity?: AlertSeverity
  unread_only?: boolean
  skip?: number
  limit?: number
}

export interface StrategyResponse {
  id: number
  user_id: number
  name: string
  description: string | null
  symbol: string
  dsl_json: string
  timeframe: string
  direction: string
  is_active: boolean
  is_builtin: boolean
  created_at: string
  updated_at: string | null
}

export interface StrategyCreate {
  name: string
  description?: string | null
  symbol: string
  dsl_json: string
  timeframe?: string
  direction?: string
}

export interface BacktestSignal {
  time: string
  type: 'entry' | 'exit' | 'flip' | 'rebalance'
  price: number
  reason?: string | null
}

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

export interface BacktestResult {
  config: Record<string, unknown>
  metrics: Record<string, number | null>
  trades: BacktestTrade[]
  equity_curve: Array<{ time: string; equity: number; close: number }>
  signals: BacktestSignal[]
  orders?: Array<Record<string, unknown>>
  contract?: Record<string, unknown>
}

export interface BacktestRunResponse {
  id: number
  strategy_id: number | null
  user_id: number
  query: string | null
  metrics_score: number | null
  trade_count: number | null
  total_return_pct: number | null
  max_drawdown_pct: number | null
  status: string
  error_message: string | null
  result_json?: string | null
  result?: BacktestResult | null
  created_at: string
  finished_at: string | null
}

export interface StrategyBacktestRequest {
  initial_cash?: number
  quantity?: number
  limit?: number
  engine_mode?: 'legacy' | 'futures'
}

export interface StrategyPortfolioPlanRequest {
  account_balance?: number | string
  risk_level?: 'low' | 'medium' | 'high'
  entry_price?: number | string | null
}

export interface StrategyPortfolioPlanResponse {
  strategy_id: number
  variety_id: number
  symbol: string
  variety_name: string
  direction: 'long' | 'short'
  account_balance: string
  risk_level: 'low' | 'medium' | 'high'
  entry_price: string
  suggested_lots: number
  suggested_quantity: number
  can_create: boolean
  stop_loss_price: string
  take_profit_price: string
  margin_required: string
  risk_amount: string
  risk_reward_ratio: string
  notes: string[]
}

// ========== Factor (因子) ==========

export interface FactorResponse {
  id: number
  package_id: string
  factor_id: string
  name: string
  source: string | null
  category: string | null
  q_score: number | null
  test_rankicir: number | null
  monotonicity: number | null
  ls_sharpe: number | null
  source_expression: string
  converted_formula: string | null
  conversion_status: string
  fields_json: string | null
  metadata_json: string | null
  is_builtin: boolean
  is_active: boolean
  user_id: number | null
  created_at: string
  updated_at: string | null
}

export interface FactorCreate {
  name: string
  category: string
  source_expression: string
  fields_json?: string
  metadata_json?: string
}

export interface FactorUpdate {
  name?: string
  category?: string
  source_expression?: string
  fields_json?: string
  metadata_json?: string
  is_active?: boolean
}

export interface FactorListParams {
  skip?: number
  limit?: number
  q?: string
  category?: string
  source?: string
  is_builtin?: boolean
}

export interface FactorListResponse {
  items: FactorResponse[]
  total: number
}

export interface FactorDeleteResponse {
  message: string
}

// ---------------------------------------------------------------------------
// Evolution API types
// ---------------------------------------------------------------------------

export interface EvolutionRunResponse {
  id: number
  user_id: number
  symbol: string
  config_json: string
  status: string
  generations: number | null
  population_size: number | null
  best_strategy_id: number | null
  summary_json: string | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string | null
}

export interface EvolutionRunListResponse {
  items: EvolutionRunResponse[]
  total: number
}

export interface GenerationSnapshotResponse {
  id: number
  generation_number: number
  best_fitness: number | null
  avg_fitness: number | null
  diversity_score: number | null
  created_at: string | null
}

export interface EvolutionRunDetailResponse extends EvolutionRunResponse {
  generations_snapshots: GenerationSnapshotResponse[]
}

export interface StrategyLifecycleResponse {
  id: number
  strategy_id: number
  source: string
  status: string
  evolution_run_id: number | null
  in_sample_metrics: Record<string, unknown> | null
  out_of_sample_metrics: Record<string, unknown> | null
  walk_forward_metrics: Record<string, unknown> | null
  decay_score: number | null
  performance_trend: number | null
  last_evaluated_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface DecayEvaluationRequest {
  strategy_id: number
  recent_metrics?: Record<string, unknown> | null
}

export interface DecayEvaluationResponse {
  strategy_id: number
  decay_score: number
  status: string
  recommended_action: string
  details: Record<string, unknown>
}

export interface LifecycleComparisonRequest {
  strategy_ids: number[]
}

export interface LifecycleComparisonItem {
  strategy_id: number
  strategy_name: string
  symbol: string
  has_lifecycle: boolean
  status: string
  decay_score: number | null
  source: string
  recommended_action: string
}

export interface LifecycleComparisonResponse {
  items: LifecycleComparisonItem[]
}

export interface TradeRecord {
  id: number
  user_id: number
  variety_id: number
  variety_symbol: string
  variety_name: string
  opinion_id: number | null
  strategy_id: number | null
  backtest_run_id: number | null
  direction: 'long' | 'short'
  entry_price: string
  exit_price: string | null
  quantity: number
  status: 'open' | 'closed'
  pnl: string | null
  pnl_percent: string | null
  unrealized_pnl: string | null
  unrealized_pnl_percent: string | null
  account_balance: string | null
  stop_loss_price: string | null
  take_profit_price: string | null
  margin_required: string | null
  risk_amount: string | null
  risk_reward_ratio: string | null
  source: 'manual' | 'strategy' | string
  closed_at: string | null
  created_at: string
}

export interface TradeRecordCreate {
  variety_id: number
  opinion_id?: number | null
  strategy_id?: number | null
  backtest_run_id?: number | null
  direction: 'long' | 'short'
  entry_price: string
  quantity?: number
  account_balance?: string | null
  stop_loss_price?: string | null
  take_profit_price?: string | null
  margin_required?: string | null
  risk_amount?: string | null
  risk_reward_ratio?: string | null
  source?: 'manual' | 'strategy'
}

export interface TradeRecordClose {
  exit_price: string
}


export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export interface ChatMessageCreate {
  content: string
}

export interface AgentTaskStepResponse {
  id: number
  task_id: number
  step_number: number
  role: string
  content: string
  tool_name: string | null
  tool_input: Record<string, unknown> | null
  tool_output: Record<string, unknown> | null
  created_at: string
}

export interface AgentTaskResponse {
  id: number
  user_id: number
  parent_task_id: number | null
  agent_type: string
  query: string
  status: string
  result: Record<string, unknown> | null
  error_message: string | null
  started_at: string | null
  finished_at: string | null
  created_at: string
  steps: AgentTaskStepResponse[]
  sub_tasks: AgentTaskResponse[]
}

export interface AgentChatRequest {
  content: string
  agent_type: string
}

export interface AgentCapabilityStatus {
  agent_type: string
  label: string
  enabled: boolean
  requires_llm: boolean
  reason: string | null
}

export interface AgentStatusSummary {
  server_time: string
  llm_configured: boolean
  total_tasks: number
  running_tasks: number
  completed_tasks: number
  failed_tasks: number
  recent_failed_tasks: AgentTaskResponse[]
  capabilities: AgentCapabilityStatus[]
}

export interface AgentPermissionHeartbeat {
  server_time: string
  authenticated: boolean
  user_id: number
  username: string
  role: string
  can_create_tasks: boolean
  can_stream_chat: boolean
  can_view_own_tasks: boolean
  can_delete_own_tasks: boolean
  allowed_agent_types: string[]
  csrf_policy: string
  token_transport: string
}
