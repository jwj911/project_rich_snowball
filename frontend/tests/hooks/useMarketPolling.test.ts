import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { useMarketPolling } from '@/hooks/useMarketPolling'

describe('useMarketPolling', () => {
  it('should fetch data on mount when enabled', async () => {
    const fetcher = vi.fn().mockResolvedValue(['item1', 'item2'])

    const { result } = renderHook(() =>
      useMarketPolling({
        enabled: true,
        fetcher,
        intervalMs: 1000,
      }),
    )

    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual(['item1', 'item2'])
    expect(result.current.heartbeat.status).toBe('healthy')
  })

  it('should not fetch when disabled', async () => {
    const fetcher = vi.fn().mockResolvedValue([])

    const { result } = renderHook(() =>
      useMarketPolling({
        enabled: false,
        fetcher,
      }),
    )

    expect(result.current.loading).toBe(false)
    expect(fetcher).not.toHaveBeenCalled()
    expect(result.current.heartbeat.status).toBe('stale')
  })

  it('should set error when fetcher fails', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('network down'))

    const { result } = renderHook(() =>
      useMarketPolling({
        enabled: true,
        fetcher,
        errorMessage: '加载失败',
      }),
    )

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.error).toBe('network down')
    expect(result.current.heartbeat.status).toBe('error')
    expect(result.current.heartbeat.failureCount).toBe(1)
  })

  it('should expose refresh function', async () => {
    const fetcher = vi.fn().mockResolvedValue(['a'])

    const { result } = renderHook(() =>
      useMarketPolling({
        enabled: true,
        fetcher,
        runOnMount: false,
      }),
    )

    expect(result.current.data).toBeNull()
    await act(async () => {
      await result.current.refresh()
    })
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(result.current.data).toEqual(['a'])
  })

  it('should track failure count on repeated errors', async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error('fail'))

    const { result } = renderHook(() =>
      useMarketPolling({
        enabled: true,
        fetcher,
      }),
    )

    await waitFor(() => expect(result.current.heartbeat.failureCount).toBe(1))
    await act(async () => {
      await result.current.refresh()
    })
    await waitFor(() => expect(result.current.heartbeat.failureCount).toBe(2))
  })
})
