import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useProductDetail } from '@/hooks/useProductDetail'
import { api } from '@/lib/api'
import { makeComment, makeProduct } from '@/tests/fixtures'

vi.mock('@/lib/api', () => ({
  api: {
    getProduct: vi.fn(),
    getRealtime: vi.fn(),
    getVariety: vi.fn(),
    getToken: vi.fn().mockReturnValue(null),
    getRealtimeBatch: vi.fn().mockResolvedValue({ quotes: [], not_found: [] }),
  },
}))

const product = makeProduct()
const comment = makeComment()

describe('useProductDetail', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('loads product detail, realtime quote, and variety id from backend APIs', async () => {
    vi.mocked(api.getProduct).mockResolvedValue({ product, comments: [comment] })
    vi.mocked(api.getRealtime).mockResolvedValue({
      symbol: 'RB',
      current_price: 3610,
      change_percent: 1.4,
      open_price: 3500,
      high: 3660,
      low: 3490,
      volume: 11000,
      updated_at: '2026-05-16T01:01:00.000Z',
      limit_up: 3800,
      limit_down: 3200,
    })
    vi.mocked(api.getVariety).mockResolvedValue({
      id: 99,
      symbol: 'RB',
      contract_code: 'RB2609',
      name: '螺纹钢',
      exchange: 'SHFE',
      category: '黑色系',
      margin_rate: 12,
      commission: 3,
      tick_size: 1,
      price_precision: 2,
    })

    const { result } = renderHook(() => useProductDetail(1, true))

    await waitFor(() => {
      expect(result.current.product?.symbol).toBe('RB')
    })

    expect(result.current.comments).toEqual([comment])
    expect(result.current.realtime?.current_price).toBe(3610)
    expect(result.current.varietyId).toBe(99)
    expect(result.current.isLoading).toBe(false)
    expect(result.current.error).toBeNull()
  })

  it('does not request when disabled', () => {
    renderHook(() => useProductDetail(1, false))

    expect(api.getProduct).not.toHaveBeenCalled()
  })

  it('reports invalid product id without requesting backend', async () => {
    const { result } = renderHook(() => useProductDetail(Number.NaN, true))

    await waitFor(() => {
      expect(result.current.error).toBe('无效的品种 ID')
    })

    expect(api.getProduct).not.toHaveBeenCalled()
    expect(result.current.isLoading).toBe(false)
  })
})
