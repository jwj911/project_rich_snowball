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
  product_id: number
  product_symbol: string | null
  product_name: string | null
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

export interface PriceLevel {
  id: number
  user_id: number
  variety_id: number
  variety_symbol: string | null
  variety_name: string | null
  type: 'support' | 'resistance'
  price: string
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
