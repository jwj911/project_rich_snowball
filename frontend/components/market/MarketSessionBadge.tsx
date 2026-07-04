'use client'

import { useMarketStatus } from '@/lib/swr-hooks'
import { getCurrentSession, MarketSession } from '@/lib/trading-hours'

const SESSION_CONFIG: Record<MarketSession, { label: string; dot: string }> = {
  day: { label: '日盘交易中', dot: 'bg-green-700' },
  night: { label: '夜盘交易中', dot: 'bg-amber-700' },
  closed: { label: '休市中', dot: 'bg-gray-600' },
}

function normalizeSession(raw: string | undefined): MarketSession {
  if (raw === 'day' || raw === 'night' || raw === 'closed') return raw
  return 'closed'
}

export default function MarketSessionBadge() {
  const { data: status } = useMarketStatus()

  const session: MarketSession = status
    ? normalizeSession(status.current_session)
    : getCurrentSession()

  const { label, dot } = SESSION_CONFIG[session]

  return (
    <span className="inline-flex items-center gap-1.5 rounded border border-gray-alpha-400 bg-gray-100 px-2 py-1 text-label-12 text-gray-800">
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {label}
    </span>
  )
}
