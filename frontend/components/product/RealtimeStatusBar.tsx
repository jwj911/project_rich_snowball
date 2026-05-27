import { Activity, AlertTriangle, Radio, RotateCw } from 'lucide-react'
import { formatDateTime, formatRelativeTime } from '@/lib/format'

type RealtimeSource = 'sse' | 'polling' | null

interface RealtimeStatusBarProps {
  source: RealtimeSource
  loading: boolean
  error: string | null
  updatedAt: string | null | undefined
  usingLiveQuote: boolean
}

export default function RealtimeStatusBar({
  source,
  loading,
  error,
  updatedAt,
  usingLiveQuote,
}: RealtimeStatusBarProps) {
  const sourceLabel = getSourceLabel(source, usingLiveQuote)
  const tone = error ? 'border-amber-500/30 bg-amber-500/10 text-amber-200' : 'border-slate-800 bg-surface text-slate-300'

  return (
    <div className={`flex flex-col gap-3 rounded-lg border px-4 py-3 text-sm sm:flex-row sm:items-center sm:justify-between ${tone}`}>
      <div className="flex min-w-0 items-center gap-2">
        {error ? <AlertTriangle size={16} /> : <Radio size={16} className="text-green-400" />}
        <span className="font-medium">{sourceLabel}</span>
        {loading ? (
          <span className="inline-flex items-center gap-1 text-xs text-slate-500">
            <RotateCw size={13} className="animate-spin" />
            连接中
          </span>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
        <span className="inline-flex items-center gap-1">
          <Activity size={13} />
          最新更新时间 {formatDateTime(updatedAt)}
        </span>
        <span>{formatRelativeTime(updatedAt)}</span>
      </div>

      {error ? <div className="text-xs text-amber-200">{error}</div> : null}
    </div>
  )
}

function getSourceLabel(source: RealtimeSource, usingLiveQuote: boolean) {
  if (source === 'sse') return '实时行情：SSE 推送'
  if (source === 'polling') return '实时行情：轮询降级'
  if (usingLiveQuote) return '实时行情：已同步'
  return '实时行情：详情快照'
}
