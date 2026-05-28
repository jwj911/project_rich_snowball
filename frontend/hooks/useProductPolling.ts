'use client'

import { useEffect, useMemo } from 'react'
import { toast } from 'sonner'
import { useProductDetail, useVariety } from '@/lib/swr-hooks'
import { useRealtimeQuotes } from './useRealtimeQuotes'

interface ProductPollingResult {
  productDetail: import('@/lib/api').ProductDetail | null
  product: import('@/lib/api').Product | null
  realtime: import('@/lib/api').RealtimeQuote | null
  varietyId: number | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useProductPolling(productId: number, enabled: boolean): ProductPollingResult {
  const {
    data: productDetail,
    error: detailError,
    isLoading,
    mutate,
  } = useProductDetail(productId, enabled)

  const symbol = productDetail?.product?.symbol
  const realtimeSymbols = useMemo(() => (symbol ? [symbol] : []), [symbol])
  const { quotes: realtimeQuotes } = useRealtimeQuotes(realtimeSymbols)

  const { data: variety } = useVariety(symbol)

  const error = detailError
    ? (detailError instanceof Error ? detailError.message : '品种详情加载失败')
    : null

  useEffect(() => {
    if (error) {
      toast.error(error)
    }
  }, [error])

  const realtime = useMemo(() => {
    if (!symbol) return null
    return realtimeQuotes.get(symbol) ?? null
  }, [symbol, realtimeQuotes])

  return {
    productDetail: productDetail ?? null,
    product: productDetail?.product ?? null,
    realtime,
    varietyId: variety?.id ?? null,
    loading: isLoading,
    error,
    refresh: async () => { await mutate() },
  }
}
