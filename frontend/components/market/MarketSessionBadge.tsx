'use client'

import { useEffect, useState } from 'react'
import { getCurrentSession, MarketSession } from '@/lib/trading-hours'

const SESSION_CONFIG: Record<MarketSession, { label: string; dot: string }> = {
  day: { label: '日盘交易中', dot: 'bg-emerald-500' },
  night: { label: '夜盘交易中', dot: 'bg-amber-500' },
  closed: { label: '休市中', dot: 'bg-slate-500' },
}

export default function MarketSessionBadge() {
  const [session, setSession] = useState<MarketSession>(getCurrentSession)

  useEffect(() => {
    // 每分钟检查一次时段变化
    const interval = setInterval(() => {
      setSession(getCurrentSession())
    }, 60_000)
    return () => clearInterval(interval)
  }, [])

  const { label, dot } = SESSION_CONFIG[session]

  return (
    <span className="inline-flex items-center gap-1.5 rounded border border-slate-700 bg-black/30 px-2 py-1 text-xs text-slate-300">
      <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
      {label}
    </span>
  )
}
