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
    vi.useFakeTimers()
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

  it('falls back to polling when no token is available', async () => {
    vi.mocked(api.getToken).mockReturnValue(null)

    const { unmount } = renderHook(() => useRealtimeQuotes(['RB']))

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.getRealtimeBatch).toHaveBeenCalledWith(['RB'])
    expect(MockEventSource.instances).toHaveLength(0)
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

  it('polls periodically in polling mode', async () => {
    vi.mocked(api.getToken).mockReturnValue(null)

    const { unmount } = renderHook(() => useRealtimeQuotes(['RB']))

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.getRealtimeBatch).toHaveBeenCalledTimes(1)

    act(() => {
      vi.advanceTimersByTime(3000)
    })

    await act(async () => {
      await Promise.resolve()
    })

    expect(api.getRealtimeBatch).toHaveBeenCalledTimes(2)
    unmount()
  })
})
