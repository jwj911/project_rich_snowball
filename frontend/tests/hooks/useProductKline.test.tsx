import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useProductKline } from '@/hooks/useProductKline'
import { api } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  api: {
    getContracts: vi.fn(),
    getContractKline: vi.fn(),
    getContinuousKline: vi.fn(),
    getMainContractKline: vi.fn(),
    getKline: vi.fn(),
  },
}))

const rows = [
  { time: '2026-05-01', open: 1, high: 2, low: 1, close: 2, volume: 100 },
]

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

    expect(api.getContinuousKline).toHaveBeenCalledWith('RB', '1d', undefined, undefined, 90, expect.objectContaining({
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

  it('loads a selected contract kline', async () => {
    vi.mocked(api.getContracts).mockResolvedValue([
      {
        id: 12,
        ts_code: 'RB2609.SHF',
        symbol: 'RB2609',
        name: '螺纹钢2609',
        fut_code: 'RB',
        exchange: 'SHFE',
        list_date: null,
        delist_date: null,
        contract_type: null,
        is_active: true,
      },
    ])
    vi.mocked(api.getContinuousKline).mockResolvedValue(rows)
    vi.mocked(api.getContractKline).mockResolvedValue(rows)

    const { result } = renderHook(() => useProductKline('RB', true, 1))

    await waitFor(() => {
      expect(result.current.selectedContractId).toBe(12)
    })

    result.current.setSelectedKlineSource('single')

    await waitFor(() => {
      expect(api.getContractKline).toHaveBeenCalledWith(12, 'D', undefined, undefined, 90, expect.objectContaining({
        signal: expect.any(AbortSignal),
      }))
    })
  })
})
