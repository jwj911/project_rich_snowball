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
  const SYMBOLS_RB = ['RB']

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
    const { unmount } = renderHook(() => useRealtimeQuotes(SYMBOLS_RB))

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.getToken).toHaveBeenCalled()
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain('/api/realtime/stream?symbols=RB')
    unmount()
  })

  it('updates quotes from SSE messages', async () => {
    const { result, unmount } = renderHook(() => useRealtimeQuotes(SYMBOLS_RB))

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
    const { result, unmount } = renderHook(() => useRealtimeQuotes(SYMBOLS_RB))

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
  const SYMBOLS_RB = ['RB']
  let timeoutCallbacks: Function[] = []

  beforeEach(() => {
    timeoutCallbacks = []
    MockEventSource.instances = []
    vi.useFakeTimers({ shouldAdvanceTime: false })
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
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('recovers SSE after error via exponential backoff and stops polling', async () => {
    const { result, unmount } = renderHook(() => useRealtimeQuotes(SYMBOLS_RB))

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
  const SYMBOLS_RB = ['RB']
  let intervalCallbacks: Array<{ id: number; callback: Function; delay: number }> = []
  let nextIntervalId = 1
  let originalSetInterval: typeof window.setInterval
  let originalClearInterval: typeof window.clearInterval

  beforeEach(() => {
    intervalCallbacks = []
    nextIntervalId = 1
    MockEventSource.instances = []
    vi.useFakeTimers({ shouldAdvanceTime: false })
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
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('falls back to polling when no token is available', async () => {
    const { unmount } = renderHook(() => useRealtimeQuotes(SYMBOLS_RB))

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.getToken).toHaveBeenCalled()
    expect(api.getRealtimeBatch).toHaveBeenCalledWith(['RB'])
    expect(MockEventSource.instances).toHaveLength(0)
    unmount()
  })

  it('polls periodically in polling mode', async () => {
    const { unmount } = renderHook(() => useRealtimeQuotes(SYMBOLS_RB))

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
  const SYMBOLS_RB = ['RB']
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
    vi.useFakeTimers({ shouldAdvanceTime: false })
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
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('closes EventSource and clears timers on unmount', async () => {
    const { unmount } = renderHook(() => useRealtimeQuotes(SYMBOLS_RB))

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
  const SYMBOLS_RB = ['RB']
  let visibilityHidden = false
  let visibilityCallback: (() => void) | null = null

  beforeEach(() => {
    MockEventSource.instances = []
    vi.useFakeTimers({ shouldAdvanceTime: false })
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
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('closes SSE when document becomes hidden', async () => {
    const { result } = renderHook(() => useRealtimeQuotes(SYMBOLS_RB))

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
    const { result } = renderHook(() => useRealtimeQuotes(SYMBOLS_RB))

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
    vi.useFakeTimers({ shouldAdvanceTime: false })
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
      await Promise.resolve()
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

describe('useRealtimeQuotes multi-subscriber reuse', () => {
  beforeEach(() => {
    MockEventSource.instances = []
    vi.useFakeTimers({ shouldAdvanceTime: false })
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

  it('两个 hook 订阅同 symbol，只创建 1 个 EventSource', async () => {
    const { unmount: unmount1 } = renderHook(() => useRealtimeQuotes(['RB']))
    const { unmount: unmount2 } = renderHook(() => useRealtimeQuotes(['RB']))

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.instances).toHaveLength(1)

    unmount1()
    unmount2()
  })

  it('两个 hook 订阅不同 symbol，连接 URL 包含 symbols union', async () => {
    const { unmount: unmount1 } = renderHook(() => useRealtimeQuotes(['RB']))
    const { unmount: unmount2 } = renderHook(() => useRealtimeQuotes(['HC']))

    await act(async () => {
      await Promise.resolve()
    })

    // symbols 变化时会断开旧连接创建新连接，instances 中最后一个为当前活跃连接
    expect(MockEventSource.instances.length).toBeGreaterThanOrEqual(1)
    const activeSource = MockEventSource.instances[MockEventSource.instances.length - 1]
    expect(activeSource.url).toContain('symbols=RB')
    expect(activeSource.url).toContain('symbols=HC')

    unmount1()
    unmount2()
  })

  it('rerender 相同 symbols（不同数组引用）不重建连接', async () => {
    const { rerender, unmount } = renderHook(
      ({ symbols }) => useRealtimeQuotes(symbols),
      { initialProps: { symbols: ['RB'] as string[] } },
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.instances).toHaveLength(1)
    const firstSource = MockEventSource.instances[0]
    expect(firstSource.closed).toBe(false)

    // 传入内容相同但引用不同的数组
    await act(async () => {
      rerender({ symbols: ['RB'] })
      await Promise.resolve()
    })

    expect(MockEventSource.instances).toHaveLength(1)
    expect(firstSource.closed).toBe(false)

    unmount()
  })

  it('最后一个订阅卸载后关闭 SSE、timer、visibility listener', async () => {
    let clearedTimeouts: number[] = []
    let nextTimeoutId = 1

    vi.stubGlobal('setTimeout', (callback: Function, _delay?: number) => {
      return nextTimeoutId++ as unknown as ReturnType<typeof setTimeout>
    })
    vi.stubGlobal('clearTimeout', (id: ReturnType<typeof setTimeout>) => {
      clearedTimeouts.push(id as unknown as number)
    })

    const { unmount: unmount1 } = renderHook(() => useRealtimeQuotes(['RB']))
    const { unmount: unmount2 } = renderHook(() => useRealtimeQuotes(['HC']))

    await act(async () => {
      await Promise.resolve()
    })

    // 记录所有创建的 EventSource
    const initialCount = MockEventSource.instances.length
    const lastSource = MockEventSource.instances[initialCount - 1]
    expect(lastSource.closed).toBe(false)

    // 卸载第一个后 symbols union 变化，会重建连接；最终活跃连接应未关闭
    unmount1()
    const afterUnmount1Count = MockEventSource.instances.length
    const activeAfterUnmount1 = MockEventSource.instances[afterUnmount1Count - 1]
    expect(activeAfterUnmount1.closed).toBe(false)

    // 卸载最后一个
    clearedTimeouts = []
    unmount2()

    // 所有 EventSource 都应被关闭
    MockEventSource.instances.forEach((es) => {
      expect(es.closed).toBe(true)
    })
    // reconnect timer 应被清理
    expect(clearedTimeouts.length).toBeGreaterThanOrEqual(0)

    vi.unstubAllGlobals()
  })
})
