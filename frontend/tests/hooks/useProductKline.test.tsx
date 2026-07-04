import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useProductKline } from '@/hooks/useProductKline'
import { api } from '@/lib/api'
import { makeFutContract, makeKline } from '@/tests/fixtures'

vi.mock('@/lib/api', () => ({
  api: {
    getContracts: vi.fn(),
    getContractKline: vi.fn(),
    getContinuousKline: vi.fn(),
    getMainContractKline: vi.fn(),
    getKline: vi.fn(),
  },
}))

const rows = [makeKline()]

describe('useProductKline', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads continuous kline by default', async () => {
    vi.mocked(api.getContracts).mockResolvedValue([])
    vi.mocked(api.getContinuousKline).mockResolvedValue(rows)

    const { result } = renderHook(() => useProductKline('RB', true, 1))

    await waitFor(() => {
      expect(result.current.klineData).toEqual(rows)
    })

    expect(api.getContracts).toHaveBeenCalledWith(1, { limit: 200 }, expect.objectContaining({
      signal: expect.any(AbortSignal),
    }))

    expect(api.getContinuousKline).toHaveBeenCalledWith('RB', '1d', '2025-01-01', '2026-07-02', 90, expect.objectContaining({
      signal: expect.any(AbortSignal),
    }))
    expect(result.current.displayedKlineSource).toBe('continuous')
    expect(result.current.displayedKlinePeriod).toBe('1d')
    expect(result.current.klineNotice).toBeNull()
  })

  it('does not request when disabled', () => {
    renderHook(() => useProductKline('RB', false, 1))

    expect(api.getContracts).not.toHaveBeenCalled()
    expect(api.getContinuousKline).not.toHaveBeenCalled()
  })

  it('aborts the active request on unmount', () => {
    let capturedSignal: AbortSignal | null | undefined
    vi.mocked(api.getContracts).mockResolvedValue([])
    vi.mocked(api.getContinuousKline).mockImplementation((_symbol, _period, _start, _end, _limit, options) => {
      capturedSignal = options?.signal
      return new Promise(() => undefined)
    })

    const { unmount } = renderHook(() => useProductKline('RB', true, 1))

    expect(capturedSignal?.aborted).toBe(false)
    unmount()
    expect(capturedSignal?.aborted).toBe(true)
  })
})
