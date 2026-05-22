import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useRealtimeQuotes } from '@/hooks/useRealtimeQuotes'
import { api } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  api: {
    getRealtimeBatch: vi.fn(),
    createRealtimeStreamToken: vi.fn(),
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

class MockBroadcastChannel {
  static instances: MockBroadcastChannel[] = []
  onmessage: ((event: MessageEvent) => void) | null = null
  closed = false
  messages: unknown[] = []

  constructor(public name: string) {
    MockBroadcastChannel.instances.push(this)
  }

  postMessage(message: unknown) {
    this.messages.push(message)
  }

  emit(message: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: message }))
  }

  close() {
    this.closed = true
  }
}

describe('useRealtimeQuotes', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockEventSource.instances = []
    MockBroadcastChannel.instances = []
    vi.stubGlobal('EventSource', MockEventSource)
    vi.stubGlobal('BroadcastChannel', undefined)
    vi.mocked(api.createRealtimeStreamToken).mockResolvedValue({
      stream_token: 'short-lived-stream-token',
      expires_in: 60,
    })
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

  it('opens SSE with a short-lived stream token instead of the stored JWT', async () => {
    const { unmount } = renderHook(() => useRealtimeQuotes(['RB']))

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.createRealtimeStreamToken).toHaveBeenCalled()
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain('/api/realtime/stream?symbols=RB')
    expect(MockEventSource.instances[0].url).toContain('token=short-lived-stream-token')
    expect(MockEventSource.instances[0].url).not.toContain('stored-jwt')
    unmount()
  })

  it('shares one SSE connection for duplicate symbol subscriptions', async () => {
    const firstHook = renderHook(() => useRealtimeQuotes(['RB', 'CU']))
    const secondHook = renderHook(() => useRealtimeQuotes(['CU', 'RB', 'RB']))

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.createRealtimeStreamToken).toHaveBeenCalledTimes(1)
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0].url).toContain('symbols=CU')
    expect(MockEventSource.instances[0].url).toContain('symbols=RB')

    act(() => {
      MockEventSource.instances[0].onopen?.()
    })

    expect(firstHook.result.current.source).toBe('sse')
    expect(secondHook.result.current.source).toBe('sse')

    firstHook.unmount()
    expect(MockEventSource.instances[0].closed).toBe(false)

    secondHook.unmount()
    expect(MockEventSource.instances[0].closed).toBe(true)
  })

  it('batches rapid SSE messages and keeps the latest quote per symbol', async () => {
    const { result, unmount } = renderHook(() => useRealtimeQuotes(['RB']))

    await act(async () => {
      await Promise.resolve()
    })

    const source = MockEventSource.instances[0]

    act(() => {
      source.onopen?.()
      source.onmessage?.(new MessageEvent('message', {
        data: JSON.stringify({ quotes: [createQuote({ current_price: 3600 })] }),
      }))
      source.onmessage?.(new MessageEvent('message', {
        data: JSON.stringify({ quotes: [createQuote({ current_price: 3612, updated_at: '2026-05-16T10:00:01' })] }),
      }))
    })

    expect(result.current.quotes.size).toBe(0)

    act(() => {
      vi.advanceTimersByTime(100)
    })

    expect(result.current.quotes.get('RB')?.current_price).toBe(3612)

    const currentQuotes = result.current.quotes

    act(() => {
      source.onmessage?.(new MessageEvent('message', {
        data: JSON.stringify({ quotes: [createQuote({ current_price: 3612, updated_at: '2026-05-16T10:00:01' })] }),
      }))
      vi.advanceTimersByTime(100)
    })

    expect(result.current.quotes).toBe(currentQuotes)
    unmount()
  })

  it('uses BroadcastChannel follower mode when another tab is already leading', async () => {
    vi.stubGlobal('BroadcastChannel', MockBroadcastChannel)
    const { result, unmount } = renderHook(() => useRealtimeQuotes(['RB']))

    expect(MockBroadcastChannel.instances).toHaveLength(1)
    expect(MockBroadcastChannel.instances[0].name).toBe('realtime-quotes:RB')

    act(() => {
      MockBroadcastChannel.instances[0].emit({
        type: 'leader',
        tabId: 'remote-leader',
        source: 'sse',
      })
      vi.advanceTimersByTime(150)
    })

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.createRealtimeStreamToken).not.toHaveBeenCalled()
    expect(MockEventSource.instances).toHaveLength(0)
    expect(result.current.source).toBe('sse')

    act(() => {
      MockBroadcastChannel.instances[0].emit({
        type: 'quotes',
        tabId: 'remote-leader',
        quotes: [createQuote({ current_price: 3620, updated_at: '2026-05-16T10:00:03' })],
      })
      vi.advanceTimersByTime(100)
    })

    expect(result.current.quotes.get('RB')?.current_price).toBe(3620)
    unmount()
    expect(MockBroadcastChannel.instances[0].closed).toBe(true)
  })

  it('falls back to polling and retries SSE after an error', async () => {
    const { result, unmount } = renderHook(() => useRealtimeQuotes(['RB']))

    await act(async () => {
      await Promise.resolve()
    })

    const first = MockEventSource.instances[0]

    await act(async () => {
      first.onerror?.()
      await Promise.resolve()
    })

    expect(api.getRealtimeBatch).toHaveBeenCalledWith(['RB'])
    expect(result.current.source).toBe('polling')

    act(() => {
      vi.advanceTimersByTime(3000)
    })

    await act(async () => {
      await Promise.resolve()
    })

    expect(MockEventSource.instances).toHaveLength(2)

    act(() => {
      MockEventSource.instances[1].onopen?.()
    })

    expect(result.current.source).toBe('sse')
    unmount()
  })
})
