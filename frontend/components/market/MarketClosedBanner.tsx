'use client'

import { AlertTriangle } from 'lucide-react'
import { getMarketStatusMessage } from '@/lib/trading-calendar'

export default function MarketClosedBanner() {
  const message = getMarketStatusMessage()
  if (!message) return null

  return (
    <div className="flex items-center gap-2 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
      <AlertTriangle size={15} />
      {message}
    </div>
  )
}
