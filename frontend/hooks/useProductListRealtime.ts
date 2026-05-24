'use client'

import { useEffect, useMemo, useState } from 'react'
import { api, Product, ProductListResponse, ProductQuery } from '@/lib/api'
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

/**
 * 产品列表 + SSE 实时价格推送
 *
 * 1. 首次加载时通过 REST API 获取完整产品列表（含 name/category 等元数据）
 * 2. 通过 SSE 订阅全部品种的实时价格更新
 * 3. 将 SSE 推送的实时价格合并到产品列表，实现无轮询刷新
 *
 * 优势：
 * - 元数据（name/category）只加载一次，不重复请求
 * - 实时价格通过 SSE 推送，无需 30 秒轮询
 * - 服务端只在数据实际更新后才推送（变更感知），大幅降低 DB 查询压力
 */
const EMPTY_RESPONSE: ProductListResponse = {
  items: [],
  total: 0,
  totalVolume: 0,
  upCount: 0,
  downCount: 0,
  categories: [],
}

export function useProductListRealtime(
  enabled: boolean,
  query: ProductQuery = {},
): UseProductListRealtimeResult {
  const [response, setResponse] = useState<ProductListResponse>(EMPTY_RESPONSE)
  const [loading, setLoading] = useState(false)
  const [initialError, setInitialError] = useState<string | null>(null)

  const loadProducts = async () => {
    if (!enabled) return
    setLoading(true)
    setInitialError(null)
    try {
      const result = await api.getProductsPage(query)
      setResponse(result)
    } catch (err) {
      setInitialError(err instanceof Error ? err.message : '产品列表加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (enabled) {
      loadProducts()
    } else {
      setResponse(EMPTY_RESPONSE)
      setInitialError(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, query.skip, query.limit, query.search, query.category, query.direction, query.sortBy, query.sortOrder])

  const symbols = useMemo(() => response.items.map((p) => p.symbol), [response.items])
  const { quotes: realtimeQuotes, source: sseSource, error: sseError } = useRealtimeQuotes(symbols)

  const mergedProducts = useMemo(() => {
    if (realtimeQuotes.size === 0) return response.items
    return response.items.map((product) => {
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
      }
    })
  }, [response.items, realtimeQuotes])

  const source: ProductListSource = useMemo(() => {
    if (loading) return 'initial'
    if (sseSource === 'sse') return 'sse'
    if (sseSource === 'polling') return 'polling'
    return 'initial'
  }, [loading, sseSource])

  const heartbeat: MarketHeartbeat = useMemo(() => {
    if (loading) return { status: 'refreshing', failureCount: 0 }
    if (initialError) return { status: 'error', failureCount: 1, message: initialError }
    if (sseError) return { status: 'error', failureCount: 1, message: sseError }
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
  }, [loading, initialError, sseError, source])

  return {
    products: mergedProducts,
    total: response.total,
    totalVolume: response.totalVolume,
    upCount: response.upCount,
    downCount: response.downCount,
    categories: response.categories,
    loading,
    source,
    error: initialError || sseError,
    heartbeat,
    refresh: loadProducts,
  }
}
