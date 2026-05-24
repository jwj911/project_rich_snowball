import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useRealtimeQuotes } from '@/hooks/useRealtimeQuotes'
import { api } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  api: {
    getRealtimeBatch: vi.fn(),
    getToken: vi.fn(),
  },
}))

function createQuote(overrides: Partial<import('@/lib/api').RealtimeQuote> = {}) {
  return {
    symbol: 'RB',
    current_price: 3600,
    change_percent: 1.2,
    open_price: 3500,
    high: 3620,
    low: 3480,
    volume: 1000,
    updated_at: '2026-05-16T10:00:00',
    limit_up: null,
    limit_down: null,
    ...overrides,
  }
}

class MockEventSource {
  static instances: MockEventSource[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  closed = false

  constructor(
    public url: string,
    public options?: EventSourceInit,
  ) {
    MockEventSource.instances.push(this)
  }

  close() {
    this.closed = true
  }
}

describe('useRealtimeQuotes', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
    vi.mocked(api.getToken).mockReturnValue('stored-jwt')
    vi.mocked(api.getRealtimeBatch).mockResolvedValue({
      quotes: [createQuote()],
      not_found: [],
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('opens SSE when a token is available', async () => {
    const { unmount } = renderHook(() => useRealtimeQuotes(['RB']))

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.getToken).toHaveBeenCalled()
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain('/api/realtime/stream?symbols=RB')
    unmount()
  })

  it('updates quotes from SSE messages', async () => {
    const { result, unmount } = renderHook(() => useRealtimeQuotes(['RB']))

    await act(async () => {
      await Promise.resolve()
    })

    const source = MockEventSource.instances[0]

    act(() => {
      source.onopen?.()
      source.onmessage?.(new MessageEvent('message', {
        data: JSON.stringify({ quotes: [createQuote({ current_price: 3612 })] }),
      }))
    })

    expect(result.current.quotes.get('RB')?.current_price).toBe(3612)
    expect(result.current.source).toBe('sse')
    unmount()
  })

  it('falls back to polling when SSE errors', async () => {
    const { result, unmount } = renderHook(() => useRealtimeQuotes(['RB']))

    await act(async () => {
      await Promise.resolve()
    })

    const source = MockEventSource.instances[0]

    await act(async () => {
      source.onerror?.()
      await Promise.resolve()
    })

    expect(api.getRealtimeBatch).toHaveBeenCalledWith(['RB'])
    expect(result.current.source).toBe('polling')
    unmount()
  })
})

describe('useRealtimeQuotes SSE reconnect', () => {
  let timeoutCallbacks: Function[] = []

  beforeEach(() => {
    timeoutCallbacks = []
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
    vi.mocked(api.getToken).mockReturnValue('stored-jwt')
    vi.mocked(api.getRealtimeBatch).mockResolvedValue({
      quotes: [createQuote()],
      not_found: [],
    })

    vi.stubGlobal('setTimeout', (callback: Function, _delay?: number) => {
      timeoutCallbacks.push(callback)
      return timeoutCallbacks.length as unknown as ReturnType<typeof setTimeout>
    })
    vi.stubGlobal('clearTimeout', () => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('recovers SSE after error via exponential backoff and stops polling', async () => {
    const symbols = ['RB']
    const { result, unmount } = renderHook(() => useRealtimeQuotes(symbols))

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.instances).toHaveLength(1)
    const firstSource = MockEventSource.instances[0]

    await act(async () => {
      firstSource.onerror?.()
      await Promise.resolve()
    })

    expect(result.current.source).toBe('polling')

    await act(async () => {
      timeoutCallbacks[0]?.()
      await Promise.resolve()
    })

    expect(MockEventSource.instances).toHaveLength(2)
    const secondSource = MockEventSource.instances[1]

    await act(async () => {
      secondSource.onopen?.()
      await Promise.resolve()
    })

    expect(result.current.source).toBe('sse')
    unmount()
  })
})

describe('useRealtimeQuotes polling mode', () => {
  let intervalCallbacks: Array<{ id: number; callback: Function; delay: number }> = []
  let nextIntervalId = 1
  let originalSetInterval: typeof window.setInterval
  let originalClearInterval: typeof window.clearInterval

  beforeEach(() => {
    intervalCallbacks = []
    nextIntervalId = 1
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
    vi.mocked(api.getToken).mockReturnValue(null)
    vi.mocked(api.getRealtimeBatch).mockResolvedValue({
      quotes: [createQuote()],
      not_found: [],
    })

    originalSetInterval = window.setInterval
    originalClearInterval = window.clearInterval

    vi.stubGlobal('setInterval', (callback: Function, delay?: number) => {
      const id = nextIntervalId++
      intervalCallbacks.push({ id, callback, delay: delay ?? 0 })
      return id as unknown as ReturnType<typeof setInterval>
    })

    vi.stubGlobal('clearInterval', (id: ReturnType<typeof setInterval>) => {
      intervalCallbacks = intervalCallbacks.filter((c) => c.id !== (id as unknown as number))
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('falls back to polling when no token is available', async () => {
    const symbols = ['RB']
    const { unmount } = renderHook(() => useRealtimeQuotes(symbols))

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.getToken).toHaveBeenCalled()
    expect(api.getRealtimeBatch).toHaveBeenCalledWith(['RB'])
    expect(MockEventSource.instances).toHaveLength(0)
    unmount()
  })

  it('polls periodically in polling mode', async () => {
    const symbols = ['RB']
    const { unmount } = renderHook(() => useRealtimeQuotes(symbols))

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.getRealtimeBatch).toHaveBeenCalledTimes(1)

    await act(async () => {
      intervalCallbacks[0]?.callback()
      await Promise.resolve()
    })

    expect(api.getRealtimeBatch).toHaveBeenCalledTimes(2)
    unmount()
  })
})
