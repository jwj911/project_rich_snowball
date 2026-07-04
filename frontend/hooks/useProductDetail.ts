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

export function useProductDetail(productSymbol: string, enabled: boolean): UseProductDetailResult {
  const [product, setProduct] = useState<Product | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [realtime, setRealtime] = useState<RealtimeQuote | null>(null)
  const [varietyId, setVarietyId] = useState<number | null>(null)

  const loadData = useCallback(async (showLoading = true, signal?: AbortSignal) => {
    if (!productSymbol || typeof productSymbol !== 'string') {
      setError('无效的品种代码')
      setIsLoading(false)
      return
    }

    if (showLoading) setIsLoading(true)

    try {
      setError(null)
      const data = await api.getProductBySymbol(productSymbol, { signal })
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
  }, [productSymbol])

  // 项目未上线，暂不启用 SSE 实时价格推送。
  // 实时接口已预留，恢复时取消下方注释即可：
  // const symbol = product?.symbol ?? ''
  // const symbols = useMemo(() => (symbol ? [symbol] : []), [symbol])
  // const { quotes: realtimeQuotes } = useRealtimeQuotes(symbols)
  // const sseRealtime = useMemo(() => { ... }, [])
  // useEffect(() => { if (sseRealtime) { setRealtime(sseRealtime) } }, [sseRealtime])

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
