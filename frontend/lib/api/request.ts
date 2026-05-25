import { ApiError } from './errors'

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8200'

const DEFAULT_TIMEOUT_MS = 15_000

export async function fetchWithTimeout(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController()
  let timedOut = false
  const timeoutId = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, timeoutMs)

  if (options.signal) {
    options.signal.addEventListener('abort', () => controller.abort())
  }

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    })
    return response
  } catch (err) {
    if (err instanceof Error && err.name === 'AbortError') {
      if (timedOut) {
        throw new ApiError('请求超时，请检查网络连接', 0, 'TIMEOUT')
      }
      throw new ApiError('请求已取消', 0, 'ABORTED')
    }
    throw new ApiError(err instanceof Error ? err.message : 'Network request failed', 0, 'NETWORK_ERROR')
  } finally {
    window.clearTimeout(timeoutId)
  }
}

export abstract class RequestCore {
  protected abstract getToken(): string | null
  protected abstract tryRefresh(): Promise<boolean>
  protected abstract clearAuthState(): void
  protected abstract emitAuthRequired(): void

  protected buildApiError(
    response: Response,
    body: { message?: string; detail?: string; code?: string },
  ) {
    const retryAfterHeader = response.headers.get('Retry-After')
    const retryAfter = retryAfterHeader ? Number.parseInt(retryAfterHeader, 10) : undefined
    const retryMessage =
      response.status === 429 && retryAfter && Number.isFinite(retryAfter)
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

    let response = await fetchWithTimeout(`${API_BASE}${url}`, {
      ...options,
      headers: buildHeaders(this.getToken()),
    })

    // 401 时尝试通过 HttpOnly refresh cookie 自动刷新一次 access token。
    if (response.status === 401) {
      const refreshed = await this.tryRefresh()
      if (refreshed) {
        response = await fetchWithTimeout(`${API_BASE}${url}`, {
          ...options,
          headers: buildHeaders(this.getToken()),
        })
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
}
