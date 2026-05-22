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
}

export interface KlineData {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
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
    if (typeof window !== 'undefined' && !token) {
      localStorage.removeItem('token')
    }
  }

  getToken(): string | null {
    if (!this.token && typeof window !== 'undefined') {
      this.token = localStorage.getItem('token')
    }
    return this.token
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

  async getProducts(): Promise<Product[]> {
    return this.request<Product[]>('/api/products')
  }

  async getProduct(id: number): Promise<ProductDetail> {
    return this.request<ProductDetail>(`/api/products/${id}`)
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

  async getRealtime(symbol: string): Promise<RealtimeQuote> {
    return this.request<RealtimeQuote>(`/api/realtime/${encodeURIComponent(symbol)}`)
  }

  async getRealtimeBatch(symbols: string[]): Promise<{ quotes: RealtimeQuote[]; not_found: string[] }> {
    if (symbols.length === 0) return { quotes: [], not_found: [] }
    const params = new URLSearchParams()
    for (const s of symbols) params.append('symbols', s)
    return this.request<{ quotes: RealtimeQuote[]; not_found: string[] }>(`/api/realtime/batch?${params.toString()}`)
  }

  async getKline(symbol: string, period: string = '1h', limit: number = 100): Promise<KlineData[]> {
    const searchParams = new URLSearchParams({
      period,
      limit: String(limit),
    })
    return this.request<KlineData[]>(`/api/kline/${encodeURIComponent(symbol)}?${searchParams.toString()}`)
  }

  async getContinuousKline(
    symbol: string,
    period: string = 'D',
    start?: string,
    end?: string,
    limit: number = 500
  ): Promise<KlineData[]> {
    const params = new URLSearchParams()
    params.append('period', period)
    params.append('limit', String(limit))
    if (start) params.append('start', start)
    if (end) params.append('end', end)
    return this.request<KlineData[]>(`/api/kline/${symbol}/continuous?${params.toString()}`)
  }

  async getMainContractKline(
    symbol: string,
    period: string = 'D',
    start?: string,
    end?: string,
    limit: number = 500
  ): Promise<KlineData[]> {
    const params = new URLSearchParams()
    params.append('period', period)
    params.append('limit', String(limit))
    if (start) params.append('start', start)
    if (end) params.append('end', end)
    return this.request<KlineData[]>(`/api/kline/${symbol}/main?${params.toString()}`)
  }

  async getVariety(symbol: string): Promise<Variety> {
    return this.request<Variety>(`/api/varieties/${symbol}`)
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

  logout() {
    this.setToken(null)
  }
}

export const api = new ApiService()
