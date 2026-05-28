'use client'

import { useEffect, useMemo, useState } from 'react'
import { RealtimeQuote } from '@/lib/api'
import { realtimeStore } from '@/lib/realtimeStore'

interface UseRealtimeQuotesResult {
  quotes: Map<string, RealtimeQuote>
  loading: boolean
  source: 'sse' | 'polling' | null
  error: string | null
}

export function useRealtimeQuotes(symbols: string[]): UseRealtimeQuotesResult {
  const [quotes, setQuotes] = useState<Map<string, RealtimeQuote>>(new Map())
  const [loading, setLoading] = useState(false)
  const [source, setSource] = useState<'sse' | 'polling' | null>(null)
  const [error, setError] = useState<string | null>(null)

  // 防御性处理：将数组转为稳定 key，避免调用方传入不同引用但内容相同的数组时触发不必要的重订阅
  const symbolsKey = useMemo(() => symbols.slice().sort().join(','), [symbols])

  useEffect(() => {
    if (symbols.length === 0) {
      setQuotes(new Map())
      setSource(null)
      setError(null)
      setLoading(false)
      return
    }

    return realtimeStore.subscribe(symbols, ({ quotes: delta, source: newSource, error: newError, loading: newLoading }) => {
      setQuotes((prev) => {
        if (delta.size === 0) return prev
        const merged = new Map(prev)
        delta.forEach((v, k) => {
          merged.set(k, v)
        })
        return merged
      })
      setSource(newSource)
      setError(newError)
      setLoading(newLoading)
    })
  }, [symbolsKey])

  return { quotes, loading, source, error }
}
