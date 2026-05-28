import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/lib/api'

function createLocalStorageMock() {
  const store = new Map<string, string>()
  return {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store.set(key, value)
    }),
    removeItem: vi.fn((key: string) => {
      store.delete(key)
    }),
    clear: vi.fn(() => {
      store.clear()
    }),
  }
}

function jsonResponse(body: unknown, init: ResponseInit = {}) {
  return new Response(JSON.stringify(body), {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
  })
}

describe('api auth and errors', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createLocalStorageMock())
    api.setToken(null)
    api.setRefreshToken(null)
    vi.stubGlobal('fetch', vi.fn())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('parses Retry-After into ApiError for rate limited writes', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(
      { detail: '请求过于频繁' },
      { status: 429, headers: { 'Retry-After': '17' } },
    ))

    await expect(api.createComment(1, 'hello')).rejects.toMatchObject({
      status: 429,
      retryAfter: 17,
      message: '请求过于频繁，请 17 秒后再试',
    })
  })

  it('shares one refresh request across concurrent 401 responses', async () => {
    api.setToken('expired-token')
    let refreshCount = 0

    vi.mocked(fetch).mockImplementation(async (input, init) => {
      const url = String(input)
      if (url.endsWith('/api/auth/refresh')) {
        refreshCount += 1
        expect(init?.credentials).toBe('include')
        expect(init?.body).toBeUndefined()
        return jsonResponse({ access_token: 'fresh-token', token_type: 'bearer', expires_in: 1800 })
      }

      if (url.endsWith('/api/auth/me')) {
        const headers = init?.headers as Record<string, string> | undefined
        if (headers?.Authorization === 'Bearer expired-token') {
          return jsonResponse({ detail: 'expired' }, { status: 401 })
        }
        return jsonResponse({ id: 1, username: 'trader001', email: 't@example.com', created_at: '2026-05-17T00:00:00' })
      }

      return jsonResponse({ detail: 'not found' }, { status: 404 })
    })

    const [first, second] = await Promise.all([api.getMe(), api.getMe()])

    expect(first.username).toBe('trader001')
    expect(second.username).toBe('trader001')
    expect(refreshCount).toBe(1)
    expect(api.getToken()).toBe('fresh-token')
    expect(api.getRefreshToken()).toBeNull()
  })

  it('emits auth events instead of redirecting after refresh fails', async () => {
    api.setToken('expired-token')
    const authListener = vi.fn()
    const modalListener = vi.fn()
    window.addEventListener('auth-session-expired', authListener)
    window.addEventListener('open-login-modal', modalListener)
    vi.mocked(fetch).mockResolvedValue(jsonResponse({ detail: 'expired' }, { status: 401 }))

    await expect(api.getMe()).rejects.toMatchObject({ status: 401 })

    expect(authListener).toHaveBeenCalledTimes(1)
    expect(modalListener).toHaveBeenCalledTimes(1)
    expect(api.getToken()).toBeNull()
    window.removeEventListener('auth-session-expired', authListener)
    window.removeEventListener('open-login-modal', modalListener)
  })

  it('uses cookie credentials on login and keeps both tokens out of localStorage', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse({
      access_token: 'access-token',
      token_type: 'bearer',
      refresh_token: null,
      expires_in: 1800,
    }))

    await api.login('trader001', 'password123')

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/auth/login'),
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
      }),
    )
    expect(localStorage.setItem).not.toHaveBeenCalledWith('token', expect.anything())
    expect(api.getToken()).toBe('access-token')
    expect(api.getRefreshToken()).toBeNull()
  })

  it('fetches a paged product list with query params and response headers', async () => {
    vi.mocked(fetch).mockResolvedValue(jsonResponse(
      [{
        id: 1,
        name: '白银',
        symbol: 'AG',
        current_price: 5400,
        change_percent: 1.2,
        open_price: 5300,
        high: 5450,
        low: 5280,
        volume: 1200,
        category: '贵金属',
        margin: null,
        commission: null,
        updated_at: '2026-05-21T10:00:00',
      }],
      {
        headers: {
          'X-Total-Count': '12',
          'X-Total-Volume': '98765',
          'X-Up-Count': '8',
          'X-Down-Count': '4',
          'X-Categories': '%E8%B4%B5%E9%87%91%E5%B1%9E,%E9%BB%91%E8%89%B2%E7%B3%BB',
        },
      },
    ))

    const result = await api.getProductsPage({
      skip: 50,
      limit: 50,
      search: 'AG',
      category: '贵金属',
      direction: 'up',
      sortBy: 'volume',
      sortOrder: 'asc',
    })

    const requestUrl = String(vi.mocked(fetch).mock.calls[0][0])
    expect(requestUrl).toContain('/api/varieties?')
    expect(requestUrl).toContain('skip=50')
    expect(requestUrl).toContain('limit=50')
    expect(requestUrl).toContain('search=AG')
    expect(requestUrl).toContain('category=%E8%B4%B5%E9%87%91%E5%B1%9E')
    expect(requestUrl).toContain('direction=up')
    expect(requestUrl).toContain('sort_by=volume')
    expect(requestUrl).toContain('sort_order=asc')
    expect(result.total).toBe(12)
    expect(result.totalVolume).toBe(98765)
    expect(result.upCount).toBe(8)
    expect(result.downCount).toBe(4)
    expect(result.categories).toEqual(['贵金属', '黑色系'])
    expect(result.items[0].symbol).toBe('AG')
  })

  it('aborts and throws TIMEOUT when fetch exceeds 15 seconds', async () => {
    const callbacks: Function[] = []
    vi.stubGlobal('setTimeout', (callback: Function) => {
      callbacks.push(callback)
      return 999 as unknown as ReturnType<typeof setTimeout>
    })
    vi.stubGlobal('clearTimeout', () => {})
    vi.mocked(fetch).mockImplementation((_input, init) => {
      return new Promise((_, reject) => {
        const signal = init?.signal as AbortSignal | undefined
        if (signal?.aborted) {
          const err = new Error('AbortError')
          err.name = 'AbortError'
          reject(err)
          return
        }
        signal?.addEventListener('abort', () => {
          const err = new Error('AbortError')
          err.name = 'AbortError'
          reject(err)
        })
      })
    })

    const promise = api.getProducts()
    callbacks.forEach((cb) => cb())

    await expect(promise).rejects.toMatchObject({
      code: 'TIMEOUT',
      message: '请求超时，请检查网络连接',
    })

    vi.unstubAllGlobals()
  })
})
