'use client'

import { useEffect, useState } from 'react'
import { AlertTriangle } from 'lucide-react'
import { api } from '@/lib/api'
import { captureMessage } from '@/lib/sentry-lite'
import { getMarketStatusMessage } from '@/lib/trading-calendar'

export default function MarketClosedBanner() {
  const [message, setMessage] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    api.getMarketStatus()
      .then((status) => {
        if (cancelled) return
        if (!status.is_trading_day) {
          setMessage(
            status.remark
              ? `今日为${status.remark}休市，显示数据为上一交易日收盘数据`
              : '今日休市，显示数据为上一交易日收盘数据',
          )
        } else if (status.current_session === 'closed') {
          setMessage('当前非交易时段，显示数据为上一交易日收盘数据')
        } else {
          setMessage(null)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          captureMessage(`交易状态查询失败: ${err instanceof Error ? err.message : '未知错误'}`, 'warning')
          setMessage(getMarketStatusMessage())
        }
      })
    return () => { cancelled = true }
  }, [])

  if (!message) return null

  return (
    <div className="flex items-center gap-2 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
      <AlertTriangle size={15} />
      {message}
    </div>
  )
}
