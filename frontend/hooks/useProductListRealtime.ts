'use client'

import { useMemo } from 'react'
import { Product, ProductQuery } from '@/lib/api'
import { useProductsPage } from '@/lib/swr-hooks'
import { useRealtimeQuotes } from './useRealtimeQuotes'
import { MarketHeartbeat } from './useMarketPolling'

export type ProductListSource = 'sse' | 'polling' | 'initial'

export interface UseProductListRealtimeResult {
  products: Product[]
  total: number
  totalVolume: number
  upCount: number
  downCount: number
  categories: string[]
  loading: boolean
  source: ProductListSource
  error: string | null
  heartbeat: MarketHeartbeat
  refresh: () => Promise<void>
}

const EMPTY_RESPONSE = {
  items: [] as Product[],
  total: 0,
  totalVolume: 0,
  upCount: 0,
  downCount: 0,
  categories: [] as string[],
}

export function useProductListRealtime(
  enabled: boolean,
  query: ProductQuery = {},
): UseProductListRealtimeResult {
  const {
    data: response,
    error: swrError,
    isLoading,
    mutate,
  } = useProductsPage(enabled ? query : null)

  const resolvedResponse = response ?? EMPTY_RESPONSE

  const symbols = useMemo(() => resolvedResponse.items.map((p) => p.symbol), [resolvedResponse.items])
  const { quotes: realtimeQuotes, source: sseSource, error: sseError } = useRealtimeQuotes(symbols)

  const mergedProducts = useMemo(() => {
    if (realtimeQuotes.size === 0) return resolvedResponse.items
    return resolvedResponse.items.map((product) => {
      const quote = realtimeQuotes.get(product.symbol)
      if (!quote) return product
      return {
        ...product,
        current_price: quote.current_price ?? product.current_price,
        change_percent: quote.change_percent ?? product.change_percent,
        open_price: quote.open_price ?? product.open_price,
        high: quote.high ?? product.high,
        low: quote.low ?? product.low,
        volume: quote.volume ?? product.volume,
        updated_at: quote.updated_at ?? product.updated_at,
        limit_up: quote.limit_up ?? product.limit_up,
        limit_down: quote.limit_down ?? product.limit_down,
      }
    })
  }, [resolvedResponse.items, realtimeQuotes])

  const source: ProductListSource = useMemo(() => {
    if (isLoading) return 'initial'
    if (sseSource === 'sse') return 'sse'
    if (sseSource === 'polling') return 'polling'
    return 'initial'
  }, [isLoading, sseSource])

  const error = swrError ? (swrError instanceof Error ? swrError.message : '产品列表加载失败') : sseError

  const heartbeat: MarketHeartbeat = useMemo(() => {
    if (isLoading) return { status: 'refreshing', failureCount: 0 }
    if (error) return { status: 'error', failureCount: 1, message: error }
    if (source === 'sse') {
      return {
        status: 'healthy',
        lastUpdatedAt: new Date().toISOString(),
        nextRefreshAt: undefined,
        failureCount: 0,
      }
    }
    if (source === 'polling') {
      return {
        status: 'healthy',
        lastUpdatedAt: new Date().toISOString(),
        nextRefreshAt: undefined,
        failureCount: 0,
        message: 'SSE 不可用，已降级到轮询',
      }
    }
    return { status: 'idle', failureCount: 0 }
  }, [isLoading, error, source])

  return {
    products: mergedProducts,
    total: resolvedResponse.total,
    totalVolume: resolvedResponse.totalVolume,
    upCount: resolvedResponse.upCount,
    downCount: resolvedResponse.downCount,
    categories: resolvedResponse.categories,
    loading: isLoading,
    source,
    error,
    heartbeat,
    refresh: async () => { await mutate() },
  }
}
