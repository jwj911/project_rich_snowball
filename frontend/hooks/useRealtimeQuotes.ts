'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { api, RealtimeQuote } from '@/lib/api'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8200'
import { MARKET } from '@/lib/constants'

const SSE_RETRY_DELAY_MS = MARKET.SSE_RETRY_DELAY_MS
const POLL_INTERVAL_MS = MARKET.SSE_FALLBACK_INTERVAL_MS

interface UseRealtimeQuotesResult {
  quotes: Map<string, RealtimeQuote>
  loading: boolean
  source: 'sse' | 'polling' | null
  error: string | null
}

function buildSseUrl(symbols: string[]): string {
  const params = new URLSearchParams()
  for (const s of symbols) params.append('symbols', s)
  return `${API_BASE}/api/realtime/stream?${params.toString()}`
}

export function useRealtimeQuotes(symbols: string[]): UseRealtimeQuotesResult {
  const [quotes, setQuotes] = useState<Map<string, RealtimeQuote>>(new Map())
  const [loading, setLoading] = useState(false)
  const [source, setSource] = useState<'sse' | 'polling' | null>(null)
  const [error, setError] = useState<string | null>(null)
  const mountedRef = useRef(true)
  const sourceRef = useRef<'sse' | 'polling' | null>(null)

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  const poll = useCallback(async () => {
    if (symbols.length === 0) {
      if (mountedRef.current) {
        setQuotes(new Map())
        setLoading(false)
      }
      return
    }

    if (mountedRef.current) setLoading(true)
    try {
      const { quotes: batchQuotes } = await api.getRealtimeBatch(symbols)
      if (!mountedRef.current) return

      const next = new Map<string, RealtimeQuote>()
      for (const quote of batchQuotes) {
        next.set(quote.symbol, quote)
      }
      setQuotes(next)
      if (sourceRef.current !== 'polling') {
        sourceRef.current = 'polling'
        setSource('polling')
      }
      setError(null)
    } catch (err) {
      if (!mountedRef.current) return
      setError(err instanceof Error ? err.message : '轮询失败')
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [symbols])

  useEffect(() => {
    if (symbols.length === 0) {
      setQuotes(new Map())
      setSource(null)
      setError(null)
      sourceRef.current = null
      return
    }

    const token = api.getToken()
    if (!token) {
      poll()
      const interval = window.setInterval(poll, POLL_INTERVAL_MS)
      return () => window.clearInterval(interval)
    }

    let es: EventSource | null = null
    let reconnectTimer: number | null = null
    let pollInterval: number | null = null
    let reconnectAttempts = 0
    const MAX_RECONNECT_DELAY = 30000

    const connectSse = () => {
      if (!mountedRef.current) return

      try {
        es = new EventSource(buildSseUrl(symbols), { withCredentials: true })

        es.onopen = () => {
          if (!mountedRef.current) return
          reconnectAttempts = 0
          sourceRef.current = 'sse'
          setSource('sse')
          setError(null)
          // SSE 连接成功后，清除轮询
          if (pollInterval) {
            window.clearInterval(pollInterval)
            pollInterval = null
          }
        }

        es.onmessage = (event) => {
          if (!mountedRef.current) return
          try {
            const data = JSON.parse(event.data)
            const batchQuotes: RealtimeQuote[] = data.quotes ?? []
            const next = new Map<string, RealtimeQuote>()
            for (const quote of batchQuotes) {
              next.set(quote.symbol, quote)
            }
            setQuotes(next)
          } catch {
            // 忽略解析失败的推送
          }
        }

        es.onerror = () => {
          if (!mountedRef.current) return
          // SSE 出错：关闭连接，启动轮询作为 fallback，并计划重连
          if (es) {
            es.close()
            es = null
          }
          if (!pollInterval) {
            sourceRef.current = 'polling'
            setSource('polling')
            setError('SSE 连接失败，已降级到轮询')
            // 立即轮询一次
            poll()
            // 启动轮询定时器
            pollInterval = window.setInterval(poll, POLL_INTERVAL_MS)
          }
          // 指数退避重连
          reconnectAttempts += 1
          const delay = Math.min(
            SSE_RETRY_DELAY_MS * 2 ** (reconnectAttempts - 1),
            MAX_RECONNECT_DELAY,
          )
          if (reconnectTimer) {
            window.clearTimeout(reconnectTimer)
          }
          reconnectTimer = window.setTimeout(connectSse, delay)
        }
      } catch {
        // EventSource 构造失败（如浏览器不支持）
        if (!pollInterval) {
          poll()
          pollInterval = window.setInterval(poll, POLL_INTERVAL_MS)
        }
      }
    }

    // 启动 SSE
    connectSse()

    const handleVisibilityChange = () => {
      if (!mountedRef.current) return
      if (document.hidden) {
        // 页面隐藏时关闭 SSE，节省资源
        if (es) {
          es.close()
          es = null
        }
      } else if (api.getToken() && !es) {
        // 页面恢复时立即尝试重连
        reconnectAttempts = 0
        if (reconnectTimer) {
          window.clearTimeout(reconnectTimer)
          reconnectTimer = null
        }
        connectSse()
      }
    }
    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      if (es) {
        es.close()
        es = null
      }
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer)
      }
      if (pollInterval) {
        window.clearInterval(pollInterval)
      }
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [symbols, poll])

  return { quotes, loading, source, error }
}
