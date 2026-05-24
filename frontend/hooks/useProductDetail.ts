'use client'

import { Dispatch, SetStateAction, useCallback, useEffect, useMemo, useState } from 'react'
import { useRealtimeQuotes } from '@/hooks/useRealtimeQuotes'
import { api, Comment, Product, RealtimeQuote } from '@/lib/api'

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

  // SSE 实时价格订阅：只在 product.symbol 确定后启用
  const symbol = product?.symbol ?? ''
  const { quotes: realtimeQuotes } = useRealtimeQuotes(symbol ? [symbol] : [])

  const sseRealtime = useMemo(() => {
    if (!symbol) return null
    return realtimeQuotes.get(symbol) ?? null
  }, [symbol, realtimeQuotes])

  useEffect(() => {
    if (!enabled) {
      setIsLoading(false)
      return
    }

    const abortController = new AbortController()
    loadData(true, abortController.signal)

    return () => abortController.abort()
  }, [enabled, loadData])

  // 当 SSE 推送新的实时价格时，覆盖本地状态
  useEffect(() => {
    if (sseRealtime) {
      setRealtime(sseRealtime)
    }
  }, [sseRealtime])

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
