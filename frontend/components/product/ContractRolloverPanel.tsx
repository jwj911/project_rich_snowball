'use client'

import { useMemo } from 'react'
import { ContractRollover } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { ArrowRight, GitCompare } from 'lucide-react'

interface ContractRolloverPanelProps {
  rollovers: ContractRollover[]
  loading?: boolean
}

export default function ContractRolloverPanel({ rollovers, loading }: ContractRolloverPanelProps) {
  const sorted = useMemo(
    () => [...rollovers].sort((a, b) => new Date(b.effective_date).getTime() - new Date(a.effective_date).getTime()),
    [rollovers],
  )

  if (loading) {
    return (
      <section className="rounded-lg border border-slate-800 bg-surface p-4">
        <div className="mb-3 h-4 w-24 animate-pulse rounded bg-slate-800" />
        <div className="space-y-2">
          <div className="h-10 animate-pulse rounded bg-slate-800" />
          <div className="h-10 animate-pulse rounded bg-slate-800" />
        </div>
      </section>
    )
  }

  if (sorted.length === 0) {
    return (
      <section className="rounded-lg border border-slate-800 bg-surface p-4">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-300">
          <GitCompare size={16} />
          合约切换
        </h2>
        <p className="mt-3 text-xs text-slate-500">暂无合约切换记录</p>
      </section>
    )
  }

  return (
    <section className="rounded-lg border border-slate-800 bg-surface p-4">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-300">
        <GitCompare size={16} />
        合约切换历史
      </h2>
      <div className="mt-3 space-y-2">
        {sorted.map((r) => (
          <div
            key={r.id}
            className="flex items-center gap-2 rounded border border-slate-800/60 bg-black/20 px-3 py-2 text-xs"
          >
            <span className="shrink-0 font-mono text-slate-400">
              {r.old_contract_code ?? '—'}
            </span>
            <ArrowRight size={12} className="shrink-0 text-slate-600" />
            <span className="shrink-0 font-mono text-slate-200">
              {r.new_contract_code ?? '—'}
            </span>
            <span className="ml-auto shrink-0 text-slate-500">
              {formatDateTime(r.effective_date)}
            </span>
          </div>
        ))}
      </div>
    </section>
  )
}
