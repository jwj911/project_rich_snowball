'use client'

import { AlertTriangle } from 'lucide-react'
import { useMarketStatus } from '@/lib/swr-hooks'
import { getMarketStatusMessage } from '@/lib/trading-calendar'

export default function MarketClosedBanner() {
  const { data: status, error } = useMarketStatus()

  let message: string | null = null

  if (status) {
    if (!status.is_trading_day) {
      message = status.remark
        ? `今日为${status.remark}休市，显示数据为上一交易日收盘数据`
        : '今日休市，显示数据为上一交易日收盘数据'
    } else if (status.current_session === 'closed') {
      message = '当前非交易时段，显示数据为上一交易日收盘数据'
    }
  } else if (error) {
    message = getMarketStatusMessage()
  }

  if (!message) return null

  return (
    <div className="flex items-center gap-2 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
      <AlertTriangle size={15} />
      {message}
    </div>
  )
}
