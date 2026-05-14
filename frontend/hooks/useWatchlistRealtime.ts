'use client'

import { useRealtimeQuotes } from './useRealtimeQuotes'
import { RealtimeQuote } from '@/lib/api'

interface UseWatchlistRealtimeResult {
  quotes: Map<string, RealtimeQuote>
  loading: boolean
}

/**
 * @deprecated 请直接使用 useRealtimeQuotes，它支持 SSE + 轮询自动降级。
 * 保留此 hook 仅作向后兼容。
 */
export function useWatchlistRealtime(symbols: string[]): UseWatchlistRealtimeResult {
  const { quotes, loading } = useRealtimeQuotes(symbols)
  return { quotes, loading }
}
