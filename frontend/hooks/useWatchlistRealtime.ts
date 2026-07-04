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
  // 项目未上线，暂不启用实时推送（SSE/轮询）。
  // 实时接口已预留，恢复时取消下方注释即可：
  // const { quotes, loading } = useRealtimeQuotes(symbols)
  // return { quotes, loading }
  return { quotes: new Map(), loading: false }
}
