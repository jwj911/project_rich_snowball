import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { usePriceLevels } from '@/hooks/usePriceLevels'
import { api } from '@/lib/api'
import { makePriceLevel } from '@/tests/fixtures'

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

function makeLevel(overrides: Partial<ReturnType<typeof makePriceLevel>> = {}) {
  return makePriceLevel({
    user_id: 2,
    variety_id: 3,
    variety_symbol: 'AU',
    variety_name: '黄金',
    price: '500.00',
    ...overrides,
  })
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

    const { result } = renderHook(() => usePriceLevels({ varietyId: 3, userId: 2, symbol: 'AU' }))

    await waitFor(() => {
      expect(result.current.levelsLoaded).toBe(true)
    })

    expect(result.current.supportLevels).toEqual([500])
    expect(result.current.resistanceLevels).toEqual([540])
    expect(result.current.levelError).toBeNull()
    expect(localStorage.setItem).toHaveBeenCalledWith(
      'price-levels:v2:2:AU:continuous:all',
      expect.stringContaining('"supportLevels":[500]'),
    )
  })

  it('creates a support level on the cloud and refreshes server truth', async () => {
    const level510 = makeLevel({ id: 3, type: 'support', price: '510.00' })
    vi.mocked(api.getPriceLevels).mockReset().mockImplementation(() => {
      if ((api.createPriceLevel as any).mock?.calls?.length === 0) {
        return Promise.resolve([])
      }
      return Promise.resolve([level510])
    })
    vi.mocked(api.createPriceLevel).mockReset().mockResolvedValue(level510)

    const { result } = renderHook(() => usePriceLevels({ varietyId: 3, userId: 2, symbol: 'AU' }))

    await waitFor(() => {
      expect(result.current.levelsLoaded).toBe(true)
    })

    await act(async () => {
      await result.current.addSupport(510)
    })

    expect(api.createPriceLevel).toHaveBeenCalledWith(3, 'support', '510.00', 'continuous', null)
    expect(result.current.supportLevels).toEqual([510])
    expect(result.current.levelError).toBeNull()
  })

  it('keeps the created level visible when the immediate refresh is temporarily empty', async () => {
    const created = makeLevel({ id: 4, type: 'support', price: '515.00' })
    vi.mocked(api.getPriceLevels).mockReset().mockResolvedValue([])
    vi.mocked(api.createPriceLevel).mockReset().mockResolvedValue(created)

    const { result } = renderHook(() => usePriceLevels({ varietyId: 3, userId: 2, symbol: 'AU' }))

    await waitFor(() => {
      expect(result.current.levelsLoaded).toBe(true)
    })

    await act(async () => {
      await result.current.addSupport(515)
    })

    expect(result.current.supportLevels).toEqual([515])
    expect(result.current.levelError).toBeNull()
  })

  it('ignores an older initial load response after a cloud mutation starts', async () => {
    const created = makeLevel({ id: 5, type: 'support', price: '520.00' })
    let resolveInitialLoad!: (levels: ReturnType<typeof makeLevel>[]) => void
    const initialLoad = new Promise<ReturnType<typeof makeLevel>[]>((resolve) => {
      resolveInitialLoad = resolve
    })

    vi.mocked(api.getPriceLevels)
      .mockReset()
      .mockImplementationOnce(() => initialLoad)
      .mockResolvedValueOnce([created])
    vi.mocked(api.createPriceLevel).mockReset().mockResolvedValue(created)

    const { result } = renderHook(() => usePriceLevels({ varietyId: 3, userId: 2, symbol: 'AU' }))

    await waitFor(() => {
      expect(api.getPriceLevels).toHaveBeenCalledTimes(1)
    })

    await act(async () => {
      await result.current.addSupport(520)
    })
    expect(result.current.supportLevels).toEqual([520])

    await act(async () => {
      resolveInitialLoad([])
    })

    expect(result.current.supportLevels).toEqual([520])
  })

  it('deletes a created level by id when the list read is temporarily stale', async () => {
    const created = makeLevel({ id: 6, type: 'support', price: '525.00' })
    vi.mocked(api.getPriceLevels).mockReset().mockResolvedValue([])
    vi.mocked(api.createPriceLevel).mockReset().mockResolvedValue(created)
    vi.mocked(api.deletePriceLevel).mockReset().mockResolvedValue(undefined)

    const { result } = renderHook(() => usePriceLevels({ varietyId: 3, userId: 2, symbol: 'AU' }))

    await waitFor(() => {
      expect(result.current.levelsLoaded).toBe(true)
    })

    await act(async () => {
      await result.current.addSupport(525)
      await result.current.removeSupport(525)
    })

    expect(api.deletePriceLevel).toHaveBeenCalledWith(6)
    expect(result.current.supportLevels).toEqual([])
  })

  it('does not bind main-scope levels to the selected contract', async () => {
    const created = makeLevel({ id: 7, type: 'resistance', price: '6100.00' })
    vi.mocked(api.getPriceLevels).mockReset().mockResolvedValueOnce([]).mockResolvedValueOnce([created])
    vi.mocked(api.createPriceLevel).mockReset().mockResolvedValue(created)

    const { result } = renderHook(() => usePriceLevels({
      varietyId: 3,
      userId: 2,
      symbol: 'AU',
      source: 'main',
      contractId: 99,
    }))

    await waitFor(() => {
      expect(result.current.levelsLoaded).toBe(true)
    })

    await act(async () => {
      await result.current.addResistance(6100)
    })

    expect(api.getPriceLevels).toHaveBeenNthCalledWith(1, 3, undefined, 'main', null)
    expect(api.createPriceLevel).toHaveBeenCalledWith(3, 'resistance', '6100.00', 'main', null)
    expect(result.current.resistanceLevels).toEqual([6100])
  })

  it('falls back to local storage when cloud create fails', async () => {
    vi.mocked(api.getPriceLevels).mockReset().mockResolvedValue([])
    vi.mocked(api.createPriceLevel).mockReset().mockRejectedValue(new Error('请求过于频繁，请 17 秒后再试'))

    const { result } = renderHook(() => usePriceLevels({ varietyId: 3, userId: 2, symbol: 'AU' }))

    await waitFor(() => {
      expect(result.current.levelsLoaded).toBe(true)
    })

    await act(async () => {
      await result.current.addResistance(550)
    })

    expect(result.current.resistanceLevels).toEqual([550])
    expect(result.current.levelError).toContain('已临时保存到本地')
    expect(localStorage.setItem).toHaveBeenLastCalledWith(
      'price-levels:v2:2:AU:continuous:all',
      expect.stringContaining('"resistanceLevels":[550]'),
    )
  })

  it('preserves rapid local fallback updates when cloud creates fail', async () => {
    vi.mocked(api.getPriceLevels).mockReset().mockResolvedValue([])
    vi.mocked(api.createPriceLevel).mockReset().mockRejectedValue(new Error('offline'))

    const { result } = renderHook(() => usePriceLevels({ varietyId: 3, userId: 2, symbol: 'AU' }))

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
      'price-levels:v2:2:AU:continuous:all',
      expect.stringContaining('"supportLevels":[510,520]'),
    )
  })

  it('uses cached levels when cloud load fails', async () => {
    vi.stubGlobal('localStorage', createLocalStorageMock({
      'price-levels:v2:2:AU:continuous:all': JSON.stringify({
        supportLevels: [490],
        resistanceLevels: [560],
      }),
    }))
    vi.mocked(api.getPriceLevels).mockReset().mockRejectedValue(new Error('network down'))

    const { result } = renderHook(() => usePriceLevels({ varietyId: 3, userId: 2, symbol: 'AU' }))

    await waitFor(() => {
      expect(result.current.levelsLoaded).toBe(true)
    })

    expect(result.current.supportLevels).toEqual([490])
    expect(result.current.resistanceLevels).toEqual([560])
    expect(result.current.levelError).toBe('云端价位加载失败，已使用本地缓存。')
  })
})
