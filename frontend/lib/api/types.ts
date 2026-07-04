export interface Product {
  id: number
  name: string
  symbol: string
  current_price: number | null
  change_percent: number | null | undefined
  open_price: number | null
  high: number | null
  low: number | null
  volume: number | null
  category: string | null
  margin: number | null
  commission: number | null
  updated_at: string
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
  created_at: string
  finished_at: string | null
}

export interface StrategyBacktestRequest {
  initial_cash?: number
  quantity?: number
  limit?: number
}


export interface TradeRecord {
  id: number
  user_id: number
  variety_id: number
  variety_symbol: string
  variety_name: string
  opinion_id: number | null
  direction: 'long' | 'short'
  entry_price: string
  exit_price: string | null
  quantity: number
  status: 'open' | 'closed'
  pnl: string | null
  pnl_percent: string | null
  unrealized_pnl: string | null
  unrealized_pnl_percent: string | null
  closed_at: string | null
  created_at: string
}

export interface TradeRecordCreate {
  variety_id: number
  opinion_id?: number | null
  direction: 'long' | 'short'
  entry_price: string
  quantity?: number
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
