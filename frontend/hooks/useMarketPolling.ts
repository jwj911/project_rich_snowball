'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { MARKET } from '@/lib/constants'

export type MarketHeartbeatStatus = 'idle' | 'refreshing' | 'healthy' | 'stale' | 'error'

export interface MarketHeartbeat {
  status: MarketHeartbeatStatus
  lastUpdatedAt?: string
  nextRefreshAt?: string
  failureCount: number
  message?: string
}

interface UseMarketPollingOptions<T> {
  enabled: boolean
  fetcher: () => Promise<T>
  intervalMs?: number
  runOnMount?: boolean
  errorMessage?: string
}

interface UseMarketPollingResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  heartbeat: MarketHeartbeat
  refresh: () => Promise<void>
  setData: (data: T) => void
}

const DEFAULT_INTERVAL_MS = MARKET.POLL_INTERVAL_MS

function getNextRefreshAt(intervalMs: number) {
  return new Date(Date.now() + intervalMs).toISOString()
}

export function useMarketPolling<T>({
  enabled,
  fetcher,
  intervalMs = DEFAULT_INTERVAL_MS,
  runOnMount = true,
  errorMessage = '行情数据加载失败',
}: UseMarketPollingOptions<T>): UseMarketPollingResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState<string | null>(null)
  const [heartbeat, setHeartbeat] = useState<MarketHeartbeat>({
    status: enabled ? 'idle' : 'stale',
    failureCount: 0,
  })
  const mountedRef = useRef(true)
  const loadingRef = useRef(false)

  useEffect(() => {
    mountedRef.current = true

    return () => {
      mountedRef.current = false
    }
  }, [])

  const refresh = useCallback(async () => {
    if (!enabled || loadingRef.current) return

    loadingRef.current = true
    setHeartbeat((current) => ({
      ...current,
      status: 'refreshing',
      message: undefined,
    }))

    try {
      const nextData = await fetcher()
      if (!mountedRef.current) return

      const now = new Date().toISOString()
      setData(nextData)
      setError(null)
      setHeartbeat({
        status: 'healthy',
        lastUpdatedAt: now,
        nextRefreshAt: getNextRefreshAt(intervalMs),
        failureCount: 0,
      })
    } catch (err) {
      if (!mountedRef.current) return

      const message = err instanceof Error ? err.message : errorMessage
      setError(message)
      setHeartbeat((current) => ({
        status: 'error',
        lastUpdatedAt: current.lastUpdatedAt,
        nextRefreshAt: getNextRefreshAt(intervalMs),
        failureCount: current.failureCount + 1,
        message,
      }))
    } finally {
      if (mountedRef.current) {
        setLoading(false)
      }
      loadingRef.current = false
    }
  }, [enabled, errorMessage, fetcher, intervalMs])

  useEffect(() => {
    if (!enabled) {
      setLoading(false)
      setHeartbeat((current) => ({
        ...current,
        status: 'stale',
        nextRefreshAt: undefined,
      }))
      return
    }

    setLoading(runOnMount)
    setHeartbeat((current) => ({
      ...current,
      status: current.lastUpdatedAt ? current.status : 'idle',
      nextRefreshAt: getNextRefreshAt(intervalMs),
    }))

    if (runOnMount) {
      refresh()
    }

    let interval = window.setInterval(refresh, intervalMs)

    const handleVisibilityChange = () => {
      if (document.hidden) {
        window.clearInterval(interval)
      } else {
        refresh()
        interval = window.setInterval(refresh, intervalMs)
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      window.clearInterval(interval)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [enabled, intervalMs, refresh, runOnMount])

  return {
    data,
    loading,
    error,
    heartbeat,
    refresh,
    setData,
  }
}
