import type { PriceLevel } from '@/lib/api'

export type PriceLevelType = 'support' | 'resistance'

export interface PriceLevelState {
  supportLevels: number[]
  resistanceLevels: number[]
}

export interface PriceLevelBatchItem {
  variety_id: number
  type: PriceLevelType
  price: string
}

export function getPriceLevelStorageKey(productId: number, userId: number | null) {
  if (!Number.isFinite(productId) || !userId) return null
  return `price-levels:v1:${userId}:${productId}`
}

export function emptyPriceLevelState(): PriceLevelState {
  return {
    supportLevels: [],
    resistanceLevels: [],
  }
}

export function normalizeLevels(value: unknown) {
  return Array.isArray(value)
    ? value.map((item) => Number(item)).filter(Number.isFinite)
    : []
}

export function sortUniqueLevels(levels: number[], direction: 'asc' | 'desc') {
  const unique = Array.from(new Set(levels.filter(Number.isFinite)))
  return unique.sort((a, b) => (direction === 'asc' ? a - b : b - a))
}

export function levelsFromApi(levels: PriceLevel[]): PriceLevelState {
  const support: number[] = []
  const resistance: number[] = []

  for (const level of levels) {
    const price = Number(level.price)
    if (!Number.isFinite(price)) continue
    if (level.type === 'support') support.push(price)
    if (level.type === 'resistance') resistance.push(price)
  }

  return {
    supportLevels: sortUniqueLevels(support, 'asc'),
    resistanceLevels: sortUniqueLevels(resistance, 'desc'),
  }
}

export function readCachedPriceLevels(storageKey: string | null): PriceLevelState {
  if (!storageKey || typeof window === 'undefined') return emptyPriceLevelState()

  try {
    const raw = window.localStorage.getItem(storageKey)
    if (!raw) return emptyPriceLevelState()
    const parsed = JSON.parse(raw)
    return {
      supportLevels: sortUniqueLevels(normalizeLevels(parsed.supportLevels), 'asc'),
      resistanceLevels: sortUniqueLevels(normalizeLevels(parsed.resistanceLevels), 'desc'),
    }
  } catch {
    return emptyPriceLevelState()
  }
}

export function writeCachedPriceLevels(storageKey: string | null, state: PriceLevelState) {
  if (!storageKey || typeof window === 'undefined') return
  window.localStorage.setItem(
    storageKey,
    JSON.stringify({
      supportLevels: state.supportLevels,
      resistanceLevels: state.resistanceLevels,
      updatedAt: new Date().toISOString(),
    }),
  )
}

export function writeApiLevelsToCache(storageKey: string | null, levels: PriceLevel[]) {
  writeCachedPriceLevels(storageKey, levelsFromApi(levels))
}

export function appendPriceLevel(state: PriceLevelState, type: PriceLevelType, price: number): PriceLevelState {
  if (type === 'support') {
    return {
      ...state,
      supportLevels: sortUniqueLevels([...state.supportLevels, price], 'asc'),
    }
  }
  return {
    ...state,
    resistanceLevels: sortUniqueLevels([...state.resistanceLevels, price], 'desc'),
  }
}

export function removePriceLevel(state: PriceLevelState, type: PriceLevelType, price: number): PriceLevelState {
  if (type === 'support') {
    return {
      ...state,
      supportLevels: state.supportLevels.filter((level) => level !== price),
    }
  }
  return {
    ...state,
    resistanceLevels: state.resistanceLevels.filter((level) => level !== price),
  }
}

export function buildPriceLevelImportBatch(varietyId: number, state: PriceLevelState): PriceLevelBatchItem[] {
  return [
    ...state.supportLevels.map((price) => ({
      variety_id: varietyId,
      type: 'support' as const,
      price: price.toFixed(2),
    })),
    ...state.resistanceLevels.map((price) => ({
      variety_id: varietyId,
      type: 'resistance' as const,
      price: price.toFixed(2),
    })),
  ]
}
