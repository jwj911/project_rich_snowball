import { RequestCore, API_BASE, fetchWithTimeout } from './request'
import { ApiError } from './errors'
import type { TokenResponse, User } from './types'

const ACCESS_TOKEN_KEY = 'futures_access_token'

export class AuthCore extends RequestCore {
  private token: string | null = null
  private refreshPromise: Promise<boolean> | null = null

  constructor() {
    super()
    if (typeof window !== 'undefined') {
      try {
        this.token = localStorage.getItem(ACCESS_TOKEN_KEY)
      } catch {
        // localStorage unavailable (e.g. private mode)
      }
    }
  }

  setToken(token: string | null) {
    this.token = token
    if (typeof window !== 'undefined') {
      try {
        if (token) {
          localStorage.setItem(ACCESS_TOKEN_KEY, token)
        } else {
          localStorage.removeItem(ACCESS_TOKEN_KEY)
        }
      } catch {
        // localStorage unavailable
      }
    }
  }

  getToken(): string | null {
    if (this.token) return this.token
    if (typeof window !== 'undefined') {
      try {
        this.token = localStorage.getItem(ACCESS_TOKEN_KEY)
      } catch {
        // localStorage unavailable
      }
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

  protected clearAuthState() {
    this.setToken(null)
    this.setRefreshToken(null)
  }

  protected emitAuthRequired() {
    if (typeof window === 'undefined') return
    window.dispatchEvent(new CustomEvent('auth-session-expired'))
    window.dispatchEvent(new Event('open-login-modal'))
  }

  protected async tryRefresh(): Promise<boolean> {
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
      const res = await fetchWithTimeout(`${API_BASE}/api/auth/refresh`, {
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
    } catch (err) {
      if (err instanceof ApiError && err.code === 'TIMEOUT') {
        return false
      }
      return false
    }
  }

  async login(username: string, password: string): Promise<TokenResponse> {
    const formData = new URLSearchParams()
    formData.append('username', username)
    formData.append('password', password)

    const response = await fetchWithTimeout(`${API_BASE}/api/auth/login`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: formData,
    })

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

  async logout(): Promise<void> {
    this.refreshPromise = null
    await fetchWithTimeout(`${API_BASE}/api/auth/logout`, {
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
