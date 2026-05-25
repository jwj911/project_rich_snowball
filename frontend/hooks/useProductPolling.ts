'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { api, Product, ProductDetail, RealtimeQuote } from '@/lib/api'
import { toast } from 'sonner'

interface ProductPollingResult {
  productDetail: ProductDetail | null
  product: Product | null
  realtime: RealtimeQuote | null
  varietyId: number | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

const POLL_INTERVAL_MS = 30_000

export function useProductPolling(productId: number, enabled: boolean): ProductPollingResult {
  const [productDetail, setProductDetail] = useState<ProductDetail | null>(null)
  const [product, setProduct] = useState<Product | null>(null)
  const [realtime, setRealtime] = useState<RealtimeQuote | null>(null)
  const [varietyId, setVarietyId] = useState<number | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)
  const mountedRef = useRef(true)
  const inFlightRef = useRef(false)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      abortRef.current?.abort()
    }
  }, [])

  const refresh = useCallback(async () => {
    if (!enabled || !Number.isFinite(productId) || inFlightRef.current) return

    inFlightRef.current = true
    if (mountedRef.current) setLoading(true)

    try {
      abortRef.current?.abort()
      const controller = new AbortController()
      abortRef.current = controller

      const data = await api.getProduct(productId, { signal: controller.signal })
      if (!mountedRef.current) return

      setProductDetail(data)
      setProduct(data.product)
      setError(null)

      if (data.product?.symbol) {
        const quote = await api.getRealtime(data.product.symbol, { signal: controller.signal }).catch(() => null)
        if (mountedRef.current) setRealtime(quote)

        try {
          const variety = await api.getVariety(data.product.symbol, { signal: controller.signal })
          if (mountedRef.current) setVarietyId(variety.id)
        } catch {
          if (mountedRef.current) setVarietyId(null)
        }
      }
    } catch (err) {
      if (!mountedRef.current) return
      const message = err instanceof Error ? err.message : '品种详情加载失败'
      setError(message)
      toast.error(message)
    } finally {
      if (mountedRef.current) setLoading(false)
      inFlightRef.current = false
    }
  }, [enabled, productId])

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      return
    }

    refresh()

    let interval = window.setInterval(refresh, POLL_INTERVAL_MS)

    const handleVisibilityChange = () => {
      if (document.hidden) {
        window.clearInterval(interval)
      } else {
        refresh()
        interval = window.setInterval(refresh, POLL_INTERVAL_MS)
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [enabled, refresh])

  return { productDetail, product, realtime, varietyId, loading, error, refresh }
}
