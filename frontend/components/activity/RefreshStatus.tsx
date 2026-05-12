'use client'

import { MarketHeartbeat } from '@/hooks/useMarketPolling'
import { formatDateTime } from '@/lib/format'
import { AlertTriangle, CheckCircle2, Clock3, RefreshCw } from 'lucide-react'

interface RefreshStatusProps {
  heartbeat: MarketHeartbeat
  onRefresh?: () => void
  className?: string
}

const statusCopy: Record<MarketHeartbeat['status'], string> = {
  idle: '等待刷新',
  refreshing: '刷新中',
  healthy: '数据正常',
  stale: '未连接',
  error: '刷新失败',
}

export default function RefreshStatus({ heartbeat, onRefresh, className = '' }: RefreshStatusProps) {
  const isRefreshing = heartbeat.status === 'refreshing'
  const isError = heartbeat.status === 'error'

  const Icon = isError ? AlertTriangle : heartbeat.status === 'healthy' ? CheckCircle2 : Clock3

  return (
    <div
      className={`flex flex-col gap-3 rounded-lg border border-slate-800 bg-black/30 px-3 py-3 text-sm text-slate-400 sm:flex-row sm:items-center sm:justify-between ${className}`}
    >
      <div className="flex min-w-0 items-center gap-2">
        <Icon size={16} className={isError ? 'text-red-300' : heartbeat.status === 'healthy' ? 'text-emerald-300' : 'text-slate-500'} />
        <div className="min-w-0">
          <div className="font-medium text-slate-200">{statusCopy[heartbeat.status]}</div>
          <div className="mt-0.5 truncate text-xs text-slate-500">
            {heartbeat.lastUpdatedAt ? `上次刷新 ${formatDateTime(heartbeat.lastUpdatedAt)}` : '尚未获取行情数据'}
            {heartbeat.failureCount > 0 ? ` · 失败 ${heartbeat.failureCount} 次` : ''}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {heartbeat.nextRefreshAt && (
          <span className="hidden font-mono text-xs text-slate-600 sm:inline">
            下次 {formatDateTime(heartbeat.nextRefreshAt)}
          </span>
        )}
        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={isRefreshing}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg border border-slate-700 px-2.5 py-1.5 text-xs text-slate-300 transition hover:border-red-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            <RefreshCw size={13} className={isRefreshing ? 'animate-spin' : ''} />
            刷新
          </button>
        )}
      </div>
    </div>
  )
}
