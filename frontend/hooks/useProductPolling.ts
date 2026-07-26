'use client'

import { useEffect } from 'react'
import { toast } from 'sonner'
import { useProductDetail, useRealtime, useVariety } from '@/lib/swr-hooks'

interface ProductPollingResult {
  productDetail: import('@/lib/api').ProductDetail | null
  product: import('@/lib/api').Product | null
  realtime: import('@/lib/api').RealtimeQuote | null
  realtimeError: string | null
  varietyId: number | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useProductPolling(productSymbol: string, enabled: boolean): ProductPollingResult {
  const {
    data: productDetail,
    error: detailError,
    isLoading,
    mutate,
  } = useProductDetail(productSymbol, enabled)

  const symbol = productDetail?.product?.symbol

  const { data: variety } = useVariety(symbol)
  const {
    data: realtime,
    error: realtimeError,
  } = useRealtime(enabled && symbol ? symbol : '')

  const error = detailError
    ? (detailError instanceof Error ? detailError.message : '品种详情加载失败')
    : null
  const realtimeErrorMessage = realtimeError
    ? (realtimeError instanceof Error ? realtimeError.message : '实时行情加载失败')
    : null

  useEffect(() => {
    if (error) {
      toast.error(error)
    }
  }, [error])

  return {
    productDetail: productDetail ?? null,
    product: productDetail?.product ?? null,
    realtime: realtime ?? null,
    realtimeError: realtimeErrorMessage,
    varietyId: variety?.id ?? null,
    loading: isLoading,
    error,
    refresh: async () => { await mutate() },
  }
}
