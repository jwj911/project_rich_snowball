import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  appendPriceLevel,
  buildPriceLevelImportBatch,
  getPriceLevelStorageKey,
  levelsFromApi,
  readCachedPriceLevels,
  removePriceLevel,
  writeCachedPriceLevels,
} from '@/lib/priceLevels'
import type { PriceLevel } from '@/lib/api'

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

describe('price level helpers', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', createLocalStorageMock())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('normalizes api levels into sorted unique support and resistance arrays', () => {
    expect(levelsFromApi([
      makeLevel({ type: 'support', price: '510.00' }),
      makeLevel({ type: 'support', price: '500.00' }),
      makeLevel({ type: 'support', price: '500.00' }),
      makeLevel({ type: 'resistance', price: '560.00' }),
      makeLevel({ type: 'resistance', price: '570.00' }),
      makeLevel({ type: 'support', price: 'not-a-number' }),
    ])).toEqual({
      supportLevels: [500, 510],
      resistanceLevels: [570, 560],
    })
  })

  it('reads and writes cached levels defensively', () => {
    const key = getPriceLevelStorageKey(9, 2)
    expect(key).toBe('price-levels:v1:2:9')

    writeCachedPriceLevels(key, {
      supportLevels: [510, 500, 500],
      resistanceLevels: [560],
    })

    expect(readCachedPriceLevels(key)).toEqual({
      supportLevels: [500, 510],
      resistanceLevels: [560],
    })
    expect(readCachedPriceLevels(null)).toEqual({
      supportLevels: [],
      resistanceLevels: [],
    })
  })

  it('updates local state and creates a cloud import batch', () => {
    const withSupport = appendPriceLevel({ supportLevels: [], resistanceLevels: [560] }, 'support', 500)
    const withoutResistance = removePriceLevel(withSupport, 'resistance', 560)

    expect(withoutResistance).toEqual({
      supportLevels: [500],
      resistanceLevels: [],
    })
    expect(buildPriceLevelImportBatch(3, withSupport)).toEqual([
      { variety_id: 3, type: 'support', price: '500.00' },
      { variety_id: 3, type: 'resistance', price: '560.00' },
    ])
  })
})
