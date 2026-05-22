import {
  createComment,
  getProduct,
  getProducts,
  getProductsPage,
  getUserComments,
} from './products'
import {
  createRealtimeStreamToken,
  getContinuousKline,
  getContractKline,
  getContracts,
  getKline,
  getMainContractKline,
  getMarketStatus,
  getRealtime,
  getRealtimeBatch,
  getVarieties,
  getVariety,
  getVarietyFees,
} from './market'
import {
  createPriceLevel,
  createPriceLevelsBatch,
  createWatchlist,
  deletePriceLevel,
  deleteWatchlist,
  getPriceLevels,
  getWatchlists,
  getWorkspace,
  updatePriceLevel,
  updateWatchlist,
} from './workspace'
import type {
  Comment,
  FutContract,
  KlineData,
  MarketStatusResponse,
  PriceLevel,
  Product,
  ProductDetail,
  ProductListResponse,
  ProductQuery,
  RealtimeQuote,
  TokenResponse,
  User,
  Variety,
  VarietyFees,
  Watchlist,
  WorkspaceSummary,
} from './types'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8200'

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code?: string,
    public retryAfter?: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

class ApiService {
  private token: string | null = null
  private refreshPromise: Promise<boolean> | null = null

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
    // Refresh tokens are intentionally stored in HttpOnly cookies by the API.
    // This method remains as a no-op compatibility shim for older tests/callers.
  }

  getRefreshToken(): string | null {
    return null
  }

  private clearAuthState() {
    this.setToken(null)
    this.setRefreshToken(null)
  }

  private emitAuthRequired() {
    if (typeof window === 'undefined') return
    window.dispatchEvent(new CustomEvent('auth-session-expired'))
    window.dispatchEvent(new Event('open-login-modal'))
  }

  private buildApiError(response: Response, body: { message?: string; detail?: string; code?: string }) {
    const retryAfterHeader = response.headers.get('Retry-After')
    const retryAfter = retryAfterHeader ? Number.parseInt(retryAfterHeader, 10) : undefined
    const retryMessage = response.status === 429 && retryAfter && Number.isFinite(retryAfter)
      ? `请求过于频繁，请 ${retryAfter} 秒后再试`
      : null
    return new ApiError(
      retryMessage || body.message || body.detail || 'Request failed',
      response.status,
      body.code,
      Number.isFinite(retryAfter) ? retryAfter : undefined,
    )
  }

  async requestRaw(url: string, options: RequestInit = {}): Promise<Response> {
    const buildHeaders = (token: string | null): Record<string, string> => {
      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...((options.headers as Record<string, string>) || {}),
      }
      if (token) {
        headers.Authorization = `Bearer ${token}`
      }
      return headers
    }

    let response: Response
    try {
      response = await fetch(`${API_BASE}${url}`, {
        ...options,
        headers: buildHeaders(this.getToken()),
      })
    } catch (err) {
      throw new ApiError(err instanceof Error ? err.message : 'Network request failed', 0, 'NETWORK_ERROR')
    }

    // 401 时尝试通过 HttpOnly refresh cookie 自动刷新一次 access token。
    if (response.status === 401) {
      const refreshed = await this.tryRefresh()
      if (refreshed) {
        try {
          response = await fetch(`${API_BASE}${url}`, {
            ...options,
            headers: buildHeaders(this.getToken()),
          })
        } catch (err) {
          throw new ApiError(err instanceof Error ? err.message : 'Network request failed', 0, 'NETWORK_ERROR')
        }
      }
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Request failed' }))
      if (response.status === 401) {
        this.clearAuthState()
        this.emitAuthRequired()
      }
      throw this.buildApiError(response, error)
    }

    return response
  }

  async request<T>(url: string, options: RequestInit = {}): Promise<T> {
    const response = await this.requestRaw(url, options)
    return response.json()
  }

  private async tryRefresh(): Promise<boolean> {
    if (this.refreshPromise) return this.refreshPromise
    this.refreshPromise = this.performRefresh().finally(() => {
      this.refreshPromise = null
    })
    return this.refreshPromise
  }

  async refreshAccessToken(): Promise<boolean> {
    return this.tryRefresh()
  }

  private async performRefresh(): Promise<boolean> {
    try {
      const res = await fetch(`${API_BASE}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
      })
      if (!res.ok) return false
      const data = await res.json()
      this.setToken(data.access_token)
      if (data.refresh_token) {
        this.setRefreshToken(data.refresh_token)
      }
      return true
    } catch {
      return false
    }
  }

  async login(username: string, password: string): Promise<TokenResponse> {
    const formData = new URLSearchParams()
    formData.append('username', username)
    formData.append('password', password)

    let response: Response
    try {
      response = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: formData,
      })
    } catch (err) {
      throw new ApiError(err instanceof Error ? err.message : 'Network request failed', 0, 'NETWORK_ERROR')
    }

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Login failed' }))
      throw this.buildApiError(response, error)
    }

    const data: TokenResponse = await response.json()
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

  getProducts(options: RequestInit = {}): Promise<Product[]> {
    return getProducts(this, options)
  }

  getProductsPage(params: ProductQuery = {}, options: RequestInit = {}): Promise<ProductListResponse> {
    return getProductsPage(this, params, options)
  }

  getProduct(id: number, options: RequestInit = {}): Promise<ProductDetail> {
    return getProduct(this, id, options)
  }

  createComment(productId: number, content: string, priceLevelId?: number): Promise<Comment> {
    return createComment(this, productId, content, priceLevelId)
  }

  getUserComments(username: string): Promise<Comment[]> {
    return getUserComments(this, username)
  }

  getRealtime(symbol: string, options: RequestInit = {}): Promise<RealtimeQuote> {
    return getRealtime(this, symbol, options)
  }

  getRealtimeBatch(symbols: string[]): Promise<{ quotes: RealtimeQuote[]; not_found: string[] }> {
    return getRealtimeBatch(this, symbols)
  }

  createRealtimeStreamToken(options: RequestInit = {}): Promise<{ stream_token: string; expires_in: number }> {
    return createRealtimeStreamToken(this, options)
  }

  getKline(
    symbol: string,
    period: string = '1h',
    limit: number = 100,
    options: RequestInit = {},
  ): Promise<KlineData[]> {
    return getKline(this, symbol, period, limit, options)
  }

  getContinuousKline(
    symbol: string,
    period: string = 'D',
    start?: string,
    end?: string,
    limit: number = 500,
    options: RequestInit = {},
  ): Promise<KlineData[]> {
    return getContinuousKline(this, symbol, period, start, end, limit, options)
  }

  getMainContractKline(
    symbol: string,
    period: string = 'D',
    start?: string,
    end?: string,
    limit: number = 500,
    options: RequestInit = {},
  ): Promise<KlineData[]> {
    return getMainContractKline(this, symbol, period, start, end, limit, options)
  }

  getContracts(
    varietyId: number,
    params?: { activeOnly?: boolean; skip?: number; limit?: number },
    options: RequestInit = {},
  ): Promise<FutContract[]> {
    return getContracts(this, varietyId, params, options)
  }

  getContractKline(
    contractId: number,
    period: string = 'D',
    start?: string,
    end?: string,
    limit: number = 500,
    options: RequestInit = {},
  ): Promise<KlineData[]> {
    return getContractKline(this, contractId, period, start, end, limit, options)
  }

  getVariety(symbol: string, options: RequestInit = {}): Promise<Variety> {
    return getVariety(this, symbol, options)
  }

  getVarieties(
    params?: { category?: string; search?: string; skip?: number; limit?: number },
    options?: RequestInit,
  ): Promise<{ items: Variety[]; total: number }> {
    return getVarieties(this, params, options)
  }

  getPriceLevels(varietyId?: number, type?: 'support' | 'resistance'): Promise<PriceLevel[]> {
    return getPriceLevels(this, varietyId, type)
  }

  createPriceLevel(
    varietyId: number,
    type: 'support' | 'resistance',
    price: string,
    note?: string,
  ): Promise<PriceLevel> {
    return createPriceLevel(this, varietyId, type, price, note)
  }

  updatePriceLevel(id: number, updates: { price?: string; note?: string }): Promise<PriceLevel> {
    return updatePriceLevel(this, id, updates)
  }

  deletePriceLevel(id: number): Promise<void> {
    return deletePriceLevel(this, id)
  }

  createPriceLevelsBatch(
    items: Array<{
      variety_id: number
      type: 'support' | 'resistance'
      price: string
      note?: string | null
    }>,
  ): Promise<{
    success: PriceLevel[]
    failed: Array<{ index: number; reason: string }>
    created_count: number
    failed_count: number
  }> {
    return createPriceLevelsBatch(this, items)
  }

  getWatchlists(varietyId?: number): Promise<Watchlist[]> {
    return getWatchlists(this, varietyId)
  }

  createWatchlist(varietyId: number, notes?: string): Promise<Watchlist> {
    return createWatchlist(this, varietyId, notes)
  }

  updateWatchlist(id: number, updates: { notes?: string; is_notified?: boolean }): Promise<Watchlist> {
    return updateWatchlist(this, id, updates)
  }

  deleteWatchlist(id: number): Promise<void> {
    return deleteWatchlist(this, id)
  }

  getWorkspace(options: RequestInit = {}): Promise<WorkspaceSummary> {
    return getWorkspace(this, options)
  }

  getVarietyFees(symbol: string): Promise<VarietyFees> {
    return getVarietyFees(this, symbol)
  }

  getMarketStatus(): Promise<MarketStatusResponse> {
    return getMarketStatus(this)
  }

  async logout(): Promise<void> {
    this.refreshPromise = null
    await fetch(`${API_BASE}/api/auth/logout`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.getToken() ?? ''}`,
      },
    }).catch(() => {})
    this.setToken(null)
  }
}

export const api = new ApiService()
