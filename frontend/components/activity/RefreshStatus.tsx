'use client'

import { useEffect, useRef, useState } from 'react'
import { MarketHeartbeat } from '@/hooks/useMarketPolling'
import { MARKET } from '@/lib/constants'
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

const STALE_THRESHOLD_MS = MARKET.STALE_THRESHOLD_MS
const DANGER_THRESHOLD_MS = MARKET.DANGER_THRESHOLD_MS

function getDataAgeStatus(heartbeat: MarketHeartbeat): 'fresh' | 'stale' | 'danger' {
  if (heartbeat.status !== 'healthy' || !heartbeat.lastUpdatedAt) return 'fresh'
  const age = Date.now() - new Date(heartbeat.lastUpdatedAt).getTime()
  if (age > DANGER_THRESHOLD_MS) return 'danger'
  if (age > STALE_THRESHOLD_MS) return 'stale'
  return 'fresh'
}

export default function RefreshStatus({ heartbeat, onRefresh, className = '' }: RefreshStatusProps) {
  const isRefreshing = heartbeat.status === 'refreshing'
  const isError = heartbeat.status === 'error'
  const ageStatus = getDataAgeStatus(heartbeat)
  const showAgeWarning = heartbeat.status === 'healthy' && ageStatus !== 'fresh'

  const [pulse, setPulse] = useState(false)
  const lastUpdatedRef = useRef(heartbeat.lastUpdatedAt)

  // 数据更新时间变化时触发脉冲动效
  useEffect(() => {
    if (heartbeat.lastUpdatedAt && heartbeat.lastUpdatedAt !== lastUpdatedRef.current) {
      lastUpdatedRef.current = heartbeat.lastUpdatedAt
      setPulse(true)
      const timer = window.setTimeout(() => setPulse(false), 800)
      return () => window.clearTimeout(timer)
    }
  }, [heartbeat.lastUpdatedAt])

  let Icon = isError ? AlertTriangle : heartbeat.status === 'healthy' ? CheckCircle2 : Clock3
  let iconClass = 'text-slate-500'
  let statusText = statusCopy[heartbeat.status]

  if (isError) {
    iconClass = 'text-red-300'
  } else if (showAgeWarning) {
    Icon = AlertTriangle
    iconClass = ageStatus === 'danger' ? 'text-red-400' : 'text-amber-400'
    statusText = ageStatus === 'danger' ? '数据已过期' : '数据稍旧'
  } else if (heartbeat.status === 'healthy') {
    iconClass = 'text-emerald-300'
  }

  return (
    <div
      className={`flex flex-col gap-3 rounded-lg border border-slate-800 bg-black/30 px-3 py-3 text-sm text-slate-400 sm:flex-row sm:items-center sm:justify-between ${className}`}
    >
      <div className="flex min-w-0 items-center gap-2">
        <Icon size={16} className={iconClass} />
        <div className="min-w-0">
          <div className="font-medium text-slate-200">{statusText}</div>
          <div
            className={`mt-0.5 truncate text-xs text-slate-500 transition-opacity duration-300 ${pulse ? 'opacity-100' : 'opacity-80'}`}
          >
            {heartbeat.lastUpdatedAt ? (
              <>
                上次刷新 {formatDateTime(heartbeat.lastUpdatedAt)}
                {showAgeWarning && (
                  <span className={ageStatus === 'danger' ? 'text-red-400' : 'text-amber-400'}>
                    {' '}
                    · 已超时
                  </span>
                )}
              </>
            ) : (
              '尚未获取行情数据'
            )}
            {heartbeat.failureCount > 0 ? ` · 失败 ${heartbeat.failureCount} 次` : ''}
          </div>
          {isError && heartbeat.message && (
            <div className="mt-1 truncate text-xs text-red-400" title={heartbeat.message}>
              {heartbeat.message}
            </div>
          )}
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
