'use client'

import { Dispatch, SetStateAction, useCallback, useEffect, useState } from 'react'
import { useMarketPolling } from '@/hooks/useMarketPolling'
import { api, Comment, Product, RealtimeQuote } from '@/lib/api'

interface ProductRefreshSnapshot {
  product: Product
  realtime: RealtimeQuote | null
}

interface UseProductDetailResult {
  product: Product | null
  comments: Comment[]
  realtime: RealtimeQuote | null
  varietyId: number | null
  isLoading: boolean
  error: string | null
  loadData: (showLoading?: boolean, signal?: AbortSignal) => Promise<void>
  setComments: Dispatch<SetStateAction<Comment[]>>
}

export function useProductDetail(productId: number, enabled: boolean): UseProductDetailResult {
  const [product, setProduct] = useState<Product | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [realtime, setRealtime] = useState<RealtimeQuote | null>(null)
  const [varietyId, setVarietyId] = useState<number | null>(null)

  const loadData = useCallback(async (showLoading = true, signal?: AbortSignal) => {
    if (!Number.isFinite(productId)) {
      setError('无效的品种 ID')
      setIsLoading(false)
      return
    }

    if (showLoading) setIsLoading(true)

    try {
      setError(null)
      const data = await api.getProduct(productId, { signal })
      if (signal?.aborted) return

      setProduct(data.product)
      setComments(data.comments)

      if (data.product?.symbol) {
        const quote = await api.getRealtime(data.product.symbol, { signal }).catch((err) => {
          if (signal?.aborted) throw err
          return null
        })
        if (signal?.aborted) return
        setRealtime(quote)

        try {
          const variety = await api.getVariety(data.product.symbol, { signal })
          if (!signal?.aborted) setVarietyId(variety.id)
        } catch (err) {
          if (signal?.aborted) throw err
          setVarietyId(null)
        }
      }
    } catch (err) {
      if (signal?.aborted) return
      setError(err instanceof Error ? err.message : '品种详情加载失败')
    } finally {
      if (!signal?.aborted) {
        setIsLoading(false)
      }
    }
  }, [productId])

  const refreshProductSnapshot = useCallback(async (signal: AbortSignal): Promise<ProductRefreshSnapshot> => {
    if (!Number.isFinite(productId)) {
      throw new Error('无效的品种 ID')
    }

    const data = await api.getProduct(productId, { signal })
    let quote: RealtimeQuote | null = null

    if (data.product?.symbol) {
      try {
        quote = await api.getRealtime(data.product.symbol, { signal })
      } catch (err) {
        if (signal.aborted) throw err
      }
    }

    return {
      product: data.product,
      realtime: quote,
    }
  }, [productId])

  const { data: refreshedProduct } = useMarketPolling<ProductRefreshSnapshot>({
    enabled,
    fetcher: refreshProductSnapshot,
    runOnMount: false,
    errorMessage: '品种详情刷新失败',
  })

  useEffect(() => {
    if (!enabled) {
      setIsLoading(false)
      return
    }

    const abortController = new AbortController()
    loadData(true, abortController.signal)

    return () => abortController.abort()
  }, [enabled, loadData])

  useEffect(() => {
    if (!refreshedProduct) return
    setProduct(refreshedProduct.product)
    setRealtime(refreshedProduct.realtime)
  }, [refreshedProduct])

  return {
    product,
    comments,
    realtime,
    varietyId,
    isLoading,
    error,
    loadData,
    setComments,
  }
}
