import useSWR from 'swr'
import { api } from '@/lib/api'

const DEFAULT_OPTIONS = {
  refreshInterval: 30_000,
  revalidateOnFocus: false,
  errorRetryCount: 3,
} as const

export function useProducts() {
  return useSWR('products', () => api.getProducts(), DEFAULT_OPTIONS)
}

export function useProduct(id: number) {
  return useSWR(`product-${id}`, () => api.getProduct(id), DEFAULT_OPTIONS)
}

export function useUserComments(username: string | null) {
  return useSWR(
    username ? `comments-user-${username}` : null,
    () => api.getUserComments(username!),
    DEFAULT_OPTIONS,
  )
}

export function useWorkspace() {
  return useSWR('workspace', () => api.getWorkspace(), DEFAULT_OPTIONS)
}

export function useWatchlists() {
  return useSWR('watchlists', () => api.getWatchlists(), DEFAULT_OPTIONS)
}

export function useRealtime(symbol: string) {
  return useSWR(
    symbol ? `realtime-${symbol}` : null,
    () => api.getRealtime(symbol),
    { ...DEFAULT_OPTIONS, refreshInterval: 10_000 },
  )
}
