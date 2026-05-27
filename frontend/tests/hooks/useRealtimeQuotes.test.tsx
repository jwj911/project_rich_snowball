import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useRealtimeQuotes } from '@/hooks/useRealtimeQuotes'
import { api } from '@/lib/api'
import { realtimeStore } from '@/lib/realtimeStore'
import { makeRealtimeQuote } from '@/tests/fixtures'

vi.mock('@/lib/api', () => ({
  api: {
    getRealtimeBatch: vi.fn(),
    getToken: vi.fn(),
  },
}))

function createQuote(overrides: Partial<import('@/lib/api').RealtimeQuote> = {}) {
  return makeRealtimeQuote(overrides)
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
    realtimeStore.resetForTest()
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

    await act(async () => {
      source.onopen?.()
      source.onmessage?.(new MessageEvent('message', {
        data: JSON.stringify({ quotes: [createQuote({ current_price: 3612 })] }),
      }))
      vi.advanceTimersByTime(100)
      await Promise.resolve()
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
    realtimeStore.resetForTest()

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
    realtimeStore.resetForTest()

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

describe('useRealtimeQuotes resource cleanup', () => {
  let clearedIntervals: number[] = []
  let clearedTimeouts: number[] = []
  let nextIntervalId = 1
  let nextTimeoutId = 1

  beforeEach(() => {
    clearedIntervals = []
    clearedTimeouts = []
    nextIntervalId = 1
    nextTimeoutId = 1
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
    vi.mocked(api.getToken).mockReturnValue('stored-jwt')
    vi.mocked(api.getRealtimeBatch).mockResolvedValue({
      quotes: [createQuote()],
      not_found: [],
    })
    realtimeStore.resetForTest()

    vi.stubGlobal('setInterval', (callback: Function, delay?: number) => {
      const id = nextIntervalId++
      return id as unknown as ReturnType<typeof setInterval>
    })

    vi.stubGlobal('clearInterval', (id: ReturnType<typeof setInterval>) => {
      clearedIntervals.push(id as unknown as number)
    })

    vi.stubGlobal('setTimeout', (callback: Function, delay?: number) => {
      const id = nextTimeoutId++
      return id as unknown as ReturnType<typeof setTimeout>
    })

    vi.stubGlobal('clearTimeout', (id: ReturnType<typeof setTimeout>) => {
      clearedTimeouts.push(id as unknown as number)
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('closes EventSource and clears timers on unmount', async () => {
    const { unmount } = renderHook(() => useRealtimeQuotes(['RB']))

    await act(async () => {
      await Promise.resolve()
    })

    const source = MockEventSource.instances[0]
    expect(source).toBeDefined()
    expect(source.closed).toBe(false)

    await act(async () => {
      source.onerror?.()
      await Promise.resolve()
    })

    unmount()

    expect(source.closed).toBe(true)
    expect(clearedIntervals.length).toBeGreaterThanOrEqual(1)
    expect(clearedTimeouts.length).toBeGreaterThanOrEqual(0)
  })
})

describe('useRealtimeQuotes visibility handling', () => {
  let visibilityHidden = false
  let visibilityCallback: (() => void) | null = null

  beforeEach(() => {
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
    vi.mocked(api.getToken).mockReturnValue('stored-jwt')
    vi.mocked(api.getRealtimeBatch).mockResolvedValue({
      quotes: [createQuote()],
      not_found: [],
    })
    realtimeStore.resetForTest()

    visibilityHidden = false
    visibilityCallback = null

    Object.defineProperty(document, 'hidden', {
      configurable: true,
      get: () => visibilityHidden,
    })

    vi.spyOn(document, 'addEventListener').mockImplementation((event, handler) => {
      if (event === 'visibilitychange') {
        visibilityCallback = handler as () => void
      }
    })

    vi.spyOn(document, 'removeEventListener').mockImplementation(() => {})
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('closes SSE when document becomes hidden', async () => {
    const { result } = renderHook(() => useRealtimeQuotes(['RB']))

    await act(async () => {
      await Promise.resolve()
    })

    const source = MockEventSource.instances[0]
    expect(source.closed).toBe(false)

    await act(async () => {
      source.onopen?.()
      await Promise.resolve()
    })

    expect(result.current.source).toBe('sse')

    await act(async () => {
      visibilityHidden = true
      visibilityCallback?.()
      await Promise.resolve()
    })

    expect(source.closed).toBe(true)
    expect(result.current.source).toBe('sse')
  })

  it('reconnects SSE when document becomes visible', async () => {
    const { result } = renderHook(() => useRealtimeQuotes(['RB']))

    await act(async () => {
      await Promise.resolve()
    })

    const firstSource = MockEventSource.instances[MockEventSource.instances.length - 1]

    await act(async () => {
      firstSource.onopen?.()
      await Promise.resolve()
    })

    expect(result.current.source).toBe('sse')

    await act(async () => {
      visibilityHidden = true
      visibilityCallback?.()
      await Promise.resolve()
    })

    expect(firstSource.closed).toBe(true)

    await act(async () => {
      visibilityHidden = false
      visibilityCallback?.()
      await Promise.resolve()
    })

    expect(MockEventSource.instances.length).toBeGreaterThanOrEqual(2)
    const secondSource = MockEventSource.instances[MockEventSource.instances.length - 1]
    expect(secondSource.closed).toBe(false)

    await act(async () => {
      secondSource.onopen?.()
      await Promise.resolve()
    })

    expect(result.current.source).toBe('sse')
  })
})

describe('useRealtimeQuotes symbol changes', () => {
  beforeEach(() => {
    MockEventSource.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
    vi.mocked(api.getToken).mockReturnValue('stored-jwt')
    vi.mocked(api.getRealtimeBatch).mockResolvedValue({
      quotes: [createQuote()],
      not_found: [],
    })
    realtimeStore.resetForTest()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('closes old SSE and opens new one when symbols change', async () => {
    const { rerender } = renderHook(
      ({ symbols }) => useRealtimeQuotes(symbols),
      { initialProps: { symbols: ['RB'] as string[] } },
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.instances).toHaveLength(1)
    const firstSource = MockEventSource.instances[0]
    expect(firstSource.url).toContain('symbols=RB')
    expect(firstSource.closed).toBe(false)

    await act(async () => {
      rerender({ symbols: ['RB', 'HC'] })
      await Promise.resolve()
    })

    expect(firstSource.closed).toBe(true)
    expect(MockEventSource.instances).toHaveLength(2)
    const secondSource = MockEventSource.instances[1]
    expect(secondSource.url).toContain('symbols=RB')
    expect(secondSource.url).toContain('symbols=HC')
  })

  it('clears quotes when symbols become empty', async () => {
    const { result, rerender } = renderHook(
      ({ symbols }) => useRealtimeQuotes(symbols),
      { initialProps: { symbols: ['RB'] as string[] } },
    )

    await act(async () => {
      await Promise.resolve()
    })

    const source = MockEventSource.instances[0]
    await act(async () => {
      source.onopen?.()
      source.onmessage?.(new MessageEvent('message', {
        data: JSON.stringify({ quotes: [createQuote({ current_price: 3612 })] }),
      }))
      vi.advanceTimersByTime(100)
    })

    expect(result.current.quotes.size).toBe(1)

    await act(async () => {
      rerender({ symbols: [] })
      await Promise.resolve()
    })

    expect(result.current.quotes.size).toBe(0)
    expect(result.current.source).toBeNull()
  })
})
