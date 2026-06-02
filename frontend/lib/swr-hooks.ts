import useSWR from 'swr'
import { api } from '@/lib/api'
import type { ProductQuery } from '@/lib/api'
import { getPreferencesFromStorage } from '@/hooks/usePreferences'

function getRefreshInterval(): number {
  const prefs = getPreferencesFromStorage()
  return (prefs.pollingIntervalSeconds ?? 30) * 1000
}

function defaultOptions() {
  return {
    refreshInterval: getRefreshInterval(),
    revalidateOnFocus: false,
    errorRetryCount: 3,
  } as const
}

export function useProducts() {
  return useSWR('products', () => api.getProducts(), defaultOptions())
}

export function useProductsPage(query: ProductQuery | null) {
  const key = query ? ['products-page', query] as const : null
  return useSWR(
    key,
    ([, q]) => api.getProductsPage(q),
    defaultOptions(),
  )
}

export function useProductBySymbol(symbol: string) {
  return useSWR(`product-${symbol}`, () => api.getProductBySymbol(symbol), defaultOptions())
}

export function useProductDetail(symbol: string, enabled = true) {
  return useSWR(
    enabled && symbol ? `product-detail-${symbol}` : null,
    () => api.getProductBySymbol(symbol),
    defaultOptions(),
  )
}

export function useContracts(varietyId: number, enabled = true) {
  return useSWR(
    enabled && Number.isFinite(varietyId) ? `contracts-${varietyId}` : null,
    () => api.getContracts(varietyId),
    defaultOptions(),
  )
}

export function useVariety(symbol: string | null | undefined) {
  return useSWR(
    symbol ? `variety-${symbol}` : null,
    () => api.getVariety(symbol!),
    defaultOptions(),
  )
}

export function useUserComments(username: string | null) {
  return useSWR(
    username ? `comments-user-${username}` : null,
    () => api.getUserComments(username!),
    defaultOptions(),
  )
}

export function useWorkspace() {
  return useSWR('workspace', () => api.getWorkspace(), defaultOptions())
}

export function useWatchlists() {
  return useSWR('watchlists', () => api.getWatchlists(), defaultOptions())
}

export function useRealtime(symbol: string) {
  return useSWR(
    symbol ? `realtime-${symbol}` : null,
    () => api.getRealtime(symbol),
    { ...defaultOptions(), refreshInterval: 10_000 },
  )
}

export function useMarketStatus(enabled = true) {
  return useSWR(
    enabled ? 'market-status' : null,
    () => api.getMarketStatus(),
    { ...defaultOptions(), refreshInterval: 60_000 },
  )
}
