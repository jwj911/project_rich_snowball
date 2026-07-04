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

  // 项目未上线，暂不启用实时推送（SSE/轮询）。
  // 实时接口已预留，恢复时取消下方注释即可：
  // const symbols = useMemo(() => resolvedResponse.items.map((p) => p.symbol), [resolvedResponse.items])
  // const { quotes: realtimeQuotes, source: sseSource, error: sseError } = useRealtimeQuotes(symbols)
  // const mergedProducts = useMemo(() => { ... }, [])
  // const source = ...
  // const error = swrError ? ... : sseError
  // const heartbeat = ...
  // return { products: mergedProducts, ... }

  const error = swrError
    ? (swrError instanceof Error ? swrError.message : '产品列表加载失败')
    : null

  const heartbeat: MarketHeartbeat = useMemo(() => {
    if (isLoading) return { status: 'refreshing', failureCount: 0 }
    if (error) return { status: 'error', failureCount: 1, message: error }
    return { status: 'idle', failureCount: 0 }
  }, [isLoading, error])

  return {
    products: resolvedResponse.items,
    total: resolvedResponse.total,
    totalVolume: resolvedResponse.totalVolume,
    upCount: resolvedResponse.upCount,
    downCount: resolvedResponse.downCount,
    categories: resolvedResponse.categories,
    loading: isLoading,
    source: 'initial',
    error,
    heartbeat,
    refresh: async () => { await mutate() },
  }
}
