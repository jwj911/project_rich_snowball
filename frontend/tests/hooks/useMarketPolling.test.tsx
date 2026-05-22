import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMarketPolling } from '@/hooks/useMarketPolling'

describe('useMarketPolling', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('loads data on mount and records a healthy heartbeat', async () => {
    const fetcher = vi.fn().mockResolvedValue(['rb', 'au'])

    const { result } = renderHook(() => useMarketPolling<string[]>({
      enabled: true,
      fetcher,
      intervalMs: 30000,
    }))

    expect(result.current.loading).toBe(true)

    await waitFor(() => {
      expect(result.current.data).toEqual(['rb', 'au'])
    })

    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBeNull()
    expect(result.current.heartbeat.status).toBe('healthy')
    expect(result.current.heartbeat.failureCount).toBe(0)
  })

  it('does not start overlapping interval requests', async () => {
    vi.useFakeTimers()

    let resolveFirst: (value: string[]) => void = () => undefined
    const fetcher = vi.fn().mockImplementation(() => new Promise<string[]>((resolve) => {
      resolveFirst = resolve
    }))

    const { result, unmount } = renderHook(() => useMarketPolling<string[]>({
      enabled: true,
      fetcher,
      intervalMs: 1000,
    }))

    expect(fetcher).toHaveBeenCalledTimes(1)

    act(() => {
      vi.advanceTimersByTime(3000)
    })

    expect(fetcher).toHaveBeenCalledTimes(1)

    await act(async () => {
      resolveFirst(['rb'])
      await Promise.resolve()
    })

    expect(result.current.data).toEqual(['rb'])

    await act(async () => {
      vi.advanceTimersByTime(1000)
    })

    expect(fetcher).toHaveBeenCalledTimes(2)
    unmount()
  })

  it('aborts the active request when unmounted', () => {
    let capturedSignal: AbortSignal | undefined
    const fetcher = vi.fn().mockImplementation((signal: AbortSignal) => {
      capturedSignal = signal
      return new Promise<string[]>(() => undefined)
    })

    const { unmount } = renderHook(() => useMarketPolling<string[]>({
      enabled: true,
      fetcher,
    }))

    if (!capturedSignal) {
      throw new Error('expected fetcher to receive an AbortSignal')
    }
    const signal = capturedSignal
    expect(signal.aborted).toBe(false)

    unmount()

    expect(signal.aborted).toBe(true)
  })
})
