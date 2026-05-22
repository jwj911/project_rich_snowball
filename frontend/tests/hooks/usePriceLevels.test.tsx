import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { usePriceLevels } from '@/hooks/usePriceLevels'
import { api, PriceLevel } from '@/lib/api'

vi.mock('@/lib/api', () => ({
  api: {
    getPriceLevels: vi.fn(),
    createPriceLevel: vi.fn(),
    createPriceLevelsBatch: vi.fn(),
    deletePriceLevel: vi.fn(),
  },
}))

function createLocalStorageMock(seed: Record<string, string> = {}) {
  const store = new Map<string, string>(Object.entries(seed))
  return {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store.set(key, value)
    }),
    removeItem: vi.fn((key: string) => {
      store.delete(key)
    }),
    clear: vi.fn(() => {
      store.clear()
    }),
  }
}

function makeLevel(overrides: Partial<PriceLevel>): PriceLevel {
  return {
    id: 1,
    user_id: 2,
    variety_id: 3,
    variety_symbol: 'AU',
    variety_name: '黄金',
    type: 'support',
    price: '500.00',
    note: null,
    source: 'manual',
    created_at: '2026-05-17T00:00:00',
    updated_at: '2026-05-17T00:00:00',
    ...overrides,
  }
}

describe('usePriceLevels', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createLocalStorageMock())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('loads cloud price levels and mirrors them to localStorage', async () => {
    vi.mocked(api.getPriceLevels).mockResolvedValue([
      makeLevel({ id: 1, type: 'support', price: '500.00' }),
      makeLevel({ id: 2, type: 'resistance', price: '540.00' }),
    ])

    const { result } = renderHook(() => usePriceLevels(3, 2, 9))

    await waitFor(() => {
      expect(result.current.levelsLoaded).toBe(true)
    })

    expect(result.current.supportLevels).toEqual([500])
    expect(result.current.resistanceLevels).toEqual([540])
    expect(result.current.levelError).toBeNull()
    expect(localStorage.setItem).toHaveBeenCalledWith(
      'price-levels:v1:2:9',
      expect.stringContaining('"supportLevels":[500]'),
    )
  })

  it('creates a support level on the cloud and refreshes server truth', async () => {
    vi.mocked(api.getPriceLevels)
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([makeLevel({ id: 3, type: 'support', price: '510.00' })])
    vi.mocked(api.createPriceLevel).mockResolvedValue(makeLevel({ id: 3, type: 'support', price: '510.00' }))

    const { result } = renderHook(() => usePriceLevels(3, 2, 9))

    await waitFor(() => {
      expect(result.current.levelsLoaded).toBe(true)
    })

    await act(async () => {
      await result.current.addSupport(510)
    })

    expect(api.createPriceLevel).toHaveBeenCalledWith(3, 'support', '510.00')
    expect(api.getPriceLevels).toHaveBeenCalledTimes(2)
    expect(result.current.supportLevels).toEqual([510])
    expect(result.current.levelError).toBeNull()
  })

  it('falls back to local storage when cloud create fails', async () => {
    vi.mocked(api.getPriceLevels).mockResolvedValue([])
    vi.mocked(api.createPriceLevel).mockRejectedValue(new Error('请求过于频繁，请 17 秒后再试'))

    const { result } = renderHook(() => usePriceLevels(3, 2, 9))

    await waitFor(() => {
      expect(result.current.levelsLoaded).toBe(true)
    })

    await act(async () => {
      await result.current.addResistance(550)
    })

    expect(result.current.resistanceLevels).toEqual([550])
    expect(result.current.levelError).toContain('已临时保存到本地')
    expect(localStorage.setItem).toHaveBeenLastCalledWith(
      'price-levels:v1:2:9',
      expect.stringContaining('"resistanceLevels":[550]'),
    )
  })

  it('preserves rapid local fallback updates when cloud creates fail', async () => {
    vi.mocked(api.getPriceLevels).mockResolvedValue([])
    vi.mocked(api.createPriceLevel).mockRejectedValue(new Error('offline'))

    const { result } = renderHook(() => usePriceLevels(3, 2, 9))

    await waitFor(() => {
      expect(result.current.levelsLoaded).toBe(true)
    })

    await act(async () => {
      await Promise.all([
        result.current.addSupport(510),
        result.current.addSupport(520),
      ])
    })

    expect(result.current.supportLevels).toEqual([510, 520])
    expect(localStorage.setItem).toHaveBeenLastCalledWith(
      'price-levels:v1:2:9',
      expect.stringContaining('"supportLevels":[510,520]'),
    )
  })

  it('uses cached levels when cloud load fails', async () => {
    vi.stubGlobal('localStorage', createLocalStorageMock({
      'price-levels:v1:2:9': JSON.stringify({
        supportLevels: [490],
        resistanceLevels: [560],
      }),
    }))
    vi.mocked(api.getPriceLevels).mockRejectedValue(new Error('network down'))

    const { result } = renderHook(() => usePriceLevels(3, 2, 9))

    await waitFor(() => {
      expect(result.current.levelsLoaded).toBe(true)
    })

    expect(result.current.supportLevels).toEqual([490])
    expect(result.current.resistanceLevels).toEqual([560])
    expect(result.current.levelError).toBe('云端价位加载失败，已使用本地缓存。')
  })
})
