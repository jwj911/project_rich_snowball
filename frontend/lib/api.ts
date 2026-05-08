const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8200'

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

  private async request<T>(url: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...(options.headers as Record<string, string> || {}),
    }

    const token = this.getToken()
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }

    const response = await fetch(`${API_BASE}${url}`, {
      ...options,
      headers,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Request failed' }))
      if (response.status === 401) {
        this.setToken(null)
      }
      throw new Error(error.message || error.detail || 'Request failed')
    }

    return response.json()
  }

  async login(username: string, password: string): Promise<{ access_token: string }> {
    const formData = new URLSearchParams()
    formData.append('username', username)
    formData.append('password', password)

    const response = await fetch(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData,
    })

    if (!response.ok) {
      const error = await response.json().catch(() => ({ message: 'Login failed' }))
      throw new Error(error.message || error.detail || 'Login failed')
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

  async createComment(productId: number, content: string): Promise<Comment> {
    return this.request<Comment>('/api/comments', {
      method: 'POST',
      body: JSON.stringify({ product_id: productId, content }),
    })
  }

  async getUserComments(username: string): Promise<Comment[]> {
    return this.request<Comment[]>(`/api/comments/user/${username}`)
  }

  async getRealtime(symbol: string): Promise<RealtimeQuote> {
    return this.request<RealtimeQuote>(`/api/realtime/${symbol}`)
  }

  async getKline(symbol: string, period: string = '1h', limit: number = 100): Promise<KlineData[]> {
    return this.request<KlineData[]>(`/api/kline/${symbol}?period=${period}&limit=${limit}`)
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

  logout() {
    this.setToken(null)
  }
}

export const api = new ApiService()
