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

export function useProductPolling(productSymbol: string, enabled: boolean): ProductPollingResult {
  const {
    data: productDetail,
    error: detailError,
    isLoading,
    mutate,
  } = useProductDetail(productSymbol, enabled)

  const symbol = productDetail?.product?.symbol

  const { data: variety } = useVariety(symbol)

  const error = detailError
    ? (detailError instanceof Error ? detailError.message : '品种详情加载失败')
    : null

  useEffect(() => {
    if (error) {
      toast.error(error)
    }
  }, [error])

  // 项目未上线，暂不启用实时推送（SSE/轮询）。
  // 实时接口已预留，恢复时取消下方注释即可：
  // const realtimeSymbols = useMemo(() => (symbol ? [symbol] : []), [symbol])
  // const { quotes: realtimeQuotes } = useRealtimeQuotes(realtimeSymbols)
  // const realtime = useMemo(() => { ... }, [])

  return {
    productDetail: productDetail ?? null,
    product: productDetail?.product ?? null,
    realtime: null,
    varietyId: variety?.id ?? null,
    loading: isLoading,
    error,
    refresh: async () => { await mutate() },
  }
}
