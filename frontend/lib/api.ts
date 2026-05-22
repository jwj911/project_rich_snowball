const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8200'

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

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

export interface Comment {
  id: number
  product_id: number
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

export interface PriceLevel {
  id: number
  user_id: number
  variety_id: number
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

export interface AuthState {
  user: User | null
  token: string | null
  isAuthenticated: boolean
}

class ApiService {
  private token: string | null = null

  setToken(token: string | null) {
    this.token = token
    if (typeof window !== 'undefined') {
      if (token) {
        localStorage.setItem('token', token)
      } else {
        localStorage.removeItem('token')
      }
    }
  }

  getToken(): string | null {
    if (!this.token && typeof window !== 'undefined') {
      this.token = localStorage.getItem('token')
    }
    return this.token
  }

  setRefreshToken(_token: string | null) {
    // 兼容性 shim：refresh token 由后端 HttpOnly Cookie 管理
  }

  getRefreshToken(): string | null {
    return null
  }

  private async request<T>(url: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    }

    const token = this.getToken()
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 15_000)

    let response: Response
    try {
      response = await fetch(`${API_BASE}${url}`, {
        ...options,
        headers,
        signal: controller.signal,
      })
    } catch (err) {
      window.clearTimeout(timeoutId)
      if (err instanceof Error && err.name === 'AbortError') {
        throw new ApiError('请求超时，请检查网络连接', 0, 'TIMEOUT')
      }
      throw new ApiError(err instanceof Error ? err.message : 'Network request failed', 0, 'NETWORK_ERROR')
    } finally {
      window.clearTimeout(timeoutId)
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Request failed' }))
      if (response.status === 401) {
        this.setToken(null)
      }
      throw new ApiError(error.message || error.detail || 'Request failed', response.status, error.code)
    }

    return response.json()
  }

  async login(username: string, password: string): Promise<{ access_token: string }> {
    const formData = new URLSearchParams()
    formData.append('username', username)
    formData.append('password', password)

    const controller = new AbortController()
    const timeoutId = window.setTimeout(() => controller.abort(), 15_000)

    let response: Response
    try {
      response = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData,
        signal: controller.signal,
      })
    } catch (err) {
      window.clearTimeout(timeoutId)
      if (err instanceof Error && err.name === 'AbortError') {
        throw new ApiError('请求超时，请检查网络连接', 0, 'TIMEOUT')
      }
      throw new ApiError(err instanceof Error ? err.message : 'Network request failed', 0, 'NETWORK_ERROR')
    } finally {
      window.clearTimeout(timeoutId)
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Login failed' }))
      throw new ApiError(error.message || error.detail || 'Login failed', response.status, error.code)
    }

    const data = await response.json()
    this.setToken(data.access_token)
    return data
  }

  async register(username: string, email: string, password: string): Promise<User> {
    return this.request<User>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, email, password }),
    })
  }

  async getMe(): Promise<User> {
    return this.request<User>('/api/auth/me')
  }

  async getProducts(options: RequestInit = {}): Promise<Product[]> {
    return this.request<Product[]>('/api/products', options)
  }

  async getProductsPage(params: { skip?: number; limit?: number; search?: string; category?: string; direction?: 'all' | 'up' | 'down'; sortBy?: string; sortOrder?: 'asc' | 'desc' } = {}, options: RequestInit = {}): Promise<{ items: Product[]; total: number; totalVolume: number; upCount: number; downCount: number; categories: string[] }> {
    const searchParams = new URLSearchParams()
    if (params.skip !== undefined) searchParams.append('skip', String(params.skip))
    if (params.limit !== undefined) searchParams.append('limit', String(params.limit))
    if (params.search) searchParams.append('search', params.search)
    if (params.category) searchParams.append('category', params.category)
    if (params.direction) searchParams.append('direction', params.direction)
    if (params.sortBy) searchParams.append('sort_by', params.sortBy)
    if (params.sortOrder) searchParams.append('sort_order', params.sortOrder)
    const qs = searchParams.toString()
    const response = await fetch(`${API_BASE}/api/products${qs ? '?' + qs : ''}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers as Record<string, string> || {}),
        ...(this.getToken() ? { Authorization: `Bearer ${this.getToken()}` } : {}),
      },
    })
    const items: Product[] = await response.json()
    const getHeader = (name: string): number => {
      const value = response.headers.get(name)
      return value ? Number.parseInt(value, 10) : 0
    }
    const categoriesHeader = response.headers.get('X-Categories')
    return {
      items,
      total: getHeader('X-Total-Count'),
      totalVolume: getHeader('X-Total-Volume'),
      upCount: getHeader('X-Up-Count'),
      downCount: getHeader('X-Down-Count'),
      categories: categoriesHeader ? decodeURIComponent(categoriesHeader).split(',') : [],
    }
  }

  async getProduct(id: number, options: RequestInit = {}): Promise<ProductDetail> {
    return this.request<ProductDetail>(`/api/products/${id}`, options)
  }

  async createComment(productId: number, content: string, priceLevelId?: number): Promise<Comment> {
    return this.request<Comment>('/api/comments', {
      method: 'POST',
      body: JSON.stringify({ product_id: productId, content, price_level_id: priceLevelId }),
    })
  }

  async getUserComments(username: string): Promise<Comment[]> {
    return this.request<Comment[]>(`/api/comments/user/${encodeURIComponent(username)}`)
  }

  async getRealtime(symbol: string, options: RequestInit = {}): Promise<RealtimeQuote> {
    return this.request<RealtimeQuote>(`/api/realtime/${encodeURIComponent(symbol)}`, options)
  }

  async getRealtimeBatch(symbols: string[]): Promise<{ quotes: RealtimeQuote[]; not_found: string[] }> {
    if (symbols.length === 0) return { quotes: [], not_found: [] }
    const params = new URLSearchParams()
    for (const s of symbols) params.append('symbols', s)
    return this.request<{ quotes: RealtimeQuote[]; not_found: string[] }>(`/api/realtime/batch?${params.toString()}`)
  }

  async getKline(symbol: string, period: string = '1h', limit: number = 100, options: RequestInit = {}): Promise<KlineData[]> {
    const searchParams = new URLSearchParams({
      period,
      limit: String(limit),
    })
    return this.request<KlineData[]>(`/api/klines/${encodeURIComponent(symbol)}?${searchParams.toString()}`, options)
  }

  async getContinuousKline(
    symbol: string,
    period: string = 'D',
    start?: string,
    end?: string,
    limit: number = 500,
    options: RequestInit = {},
  ): Promise<KlineData[]> {
    const params = new URLSearchParams()
    params.append('period', period)
    params.append('limit', String(limit))
    if (start) params.append('start', start)
    if (end) params.append('end', end)
    return this.request<KlineData[]>(`/api/klines/${symbol}/continuous?${params.toString()}`, options)
  }

  async getMainContractKline(
    symbol: string,
    period: string = 'D',
    start?: string,
    end?: string,
    limit: number = 500,
    options: RequestInit = {},
  ): Promise<KlineData[]> {
    const params = new URLSearchParams()
    params.append('period', period)
    params.append('limit', String(limit))
    if (start) params.append('start', start)
    if (end) params.append('end', end)
    return this.request<KlineData[]>(`/api/klines/${symbol}/main?${params.toString()}`, options)
  }

  async getContractKline(
    contractId: number,
    period: string = 'D',
    start?: string,
    end?: string,
    limit: number = 500,
    options: RequestInit = {},
  ): Promise<KlineData[]> {
    const params = new URLSearchParams()
    params.append('period', period)
    params.append('limit', String(limit))
    if (start) params.append('start', start)
    if (end) params.append('end', end)
    return this.request<KlineData[]>(`/api/contracts/${contractId}/kline?${params.toString()}`, options)
  }

  async getVariety(symbol: string, options: RequestInit = {}): Promise<Variety> {
    return this.request<Variety>(`/api/varieties/${symbol}`, options)
  }

  async getVarieties(params?: { category?: string; search?: string; skip?: number; limit?: number }): Promise<Variety[]> {
    const searchParams = new URLSearchParams()
    if (params?.category) searchParams.append('category', params.category)
    if (params?.search) searchParams.append('search', params.search)
    if (params?.skip !== undefined) searchParams.append('skip', String(params.skip))
    if (params?.limit !== undefined) searchParams.append('limit', String(params.limit))
    const qs = searchParams.toString()
    return this.request<Variety[]>(`/api/varieties${qs ? '?' + qs : ''}`)
  }

  // ========== Price Levels ==========
  async getPriceLevels(varietyId?: number, type?: 'support' | 'resistance'): Promise<PriceLevel[]> {
    const searchParams = new URLSearchParams()
    if (varietyId !== undefined) searchParams.append('variety_id', String(varietyId))
    if (type) searchParams.append('type', type)
    const qs = searchParams.toString()
    return this.request<PriceLevel[]>(`/api/price-levels${qs ? '?' + qs : ''}`)
  }

  async createPriceLevel(varietyId: number, type: 'support' | 'resistance', price: string, note?: string): Promise<PriceLevel> {
    return this.request<PriceLevel>('/api/price-levels', {
      method: 'POST',
      body: JSON.stringify({ variety_id: varietyId, type, price, note }),
    })
  }

  async updatePriceLevel(id: number, updates: { price?: string; note?: string }): Promise<PriceLevel> {
    return this.request<PriceLevel>(`/api/price-levels/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    })
  }

  async deletePriceLevel(id: number): Promise<void> {
    return this.request<void>(`/api/price-levels/${id}`, { method: 'DELETE' })
  }

  // ========== Watchlists ==========
  async getWatchlists(varietyId?: number): Promise<Watchlist[]> {
    const searchParams = new URLSearchParams()
    if (varietyId !== undefined) searchParams.append('variety_id', String(varietyId))
    const qs = searchParams.toString()
    return this.request<Watchlist[]>(`/api/watchlists${qs ? '?' + qs : ''}`)
  }

  async createWatchlist(varietyId: number, notes?: string): Promise<Watchlist> {
    return this.request<Watchlist>('/api/watchlists', {
      method: 'POST',
      body: JSON.stringify({ variety_id: varietyId, notes }),
    })
  }

  async updateWatchlist(id: number, updates: { notes?: string; is_notified?: boolean }): Promise<Watchlist> {
    return this.request<Watchlist>(`/api/watchlists/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    })
  }

  async deleteWatchlist(id: number): Promise<void> {
    return this.request<void>(`/api/watchlists/${id}`, { method: 'DELETE' })
  }

  // ========== Workspace ==========
  async getWorkspace(): Promise<WorkspaceSummary> {
    return this.request<WorkspaceSummary>('/api/workspace/me')
  }

  async getMarketStatus(): Promise<{ date: string; is_trading_day: boolean; current_session: string; next_trade_date: string | null; remark: string | null }> {
    return this.request('/api/market/status')
  }

  async getVarietyFees(symbol: string): Promise<{ margin_rate: number | null; margin_amount: number | null; commission_open: number | null; commission_close: number | null; commission_close_today: number | null; unit: string | null; updated_at: string | null }> {
    return this.request(`/api/varieties/${encodeURIComponent(symbol)}/fees`)
  }

  async getContracts(varietyId: number, params?: { activeOnly?: boolean; skip?: number; limit?: number }, options: RequestInit = {}): Promise<FutContract[]> {
    const searchParams = new URLSearchParams()
    searchParams.append('variety_id', String(varietyId))
    if (params?.activeOnly !== undefined) searchParams.append('active_only', String(params.activeOnly))
    if (params?.skip !== undefined) searchParams.append('skip', String(params.skip))
    if (params?.limit !== undefined) searchParams.append('limit', String(params.limit))
    return this.request<FutContract[]>(`/api/contracts?${searchParams.toString()}`, options)
  }

  logout() {
    this.setToken(null)
  }
}

export const api = new ApiService()
