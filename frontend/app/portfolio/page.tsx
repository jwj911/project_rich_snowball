'use client'

import { useCallback, useMemo, useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import AppShell from '@/components/layout/AppShell'
import ErrorState from '@/components/ui/ErrorState'
import EmptyState from '@/components/ui/EmptyState'
import { api, type TradeRecord } from '@/lib/api'
import { formatPrice } from '@/lib/format'
import { BarChart3, Briefcase, ShieldCheck, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

type PortfolioStatus = 'all' | 'open' | 'closed'

const statusFilters: { key: PortfolioStatus; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'open', label: '持仓中' },
  { key: 'closed', label: '已平仓' },
]

const inputClass =
  'w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none transition focus:border-amber-500/50'

export default function PortfolioPage() {
  const [statusFilter, setStatusFilter] = useState<PortfolioStatus>('all')
  const [closingId, setClosingId] = useState<number | null>(null)

  const {
    data: records,
    error,
    isLoading,
    mutate,
  } = useSWR(
    ['portfolio', statusFilter],
    () =>
      api.getPortfolio({
        status: statusFilter === 'all' ? undefined : statusFilter,
        limit: 100,
      }),
    { revalidateOnFocus: false },
  )

  const stats = useMemo(() => {
    if (!records) return null
    const closed = records.filter((record) => record.status === 'closed')
    const open = records.filter((record) => record.status === 'open')
    const totalPnl = closed.reduce((sum, record) => sum + Number(record.pnl ?? 0), 0)
    const openUnrealized = open.reduce((sum, record) => sum + Number(record.unrealized_pnl ?? 0), 0)
    const winCount = closed.filter((record) => Number(record.pnl ?? 0) > 0).length
    const winRate = closed.length > 0 ? (winCount / closed.length) * 100 : 0
    return { totalPnl, openUnrealized, winRate, closedCount: closed.length, openCount: open.length }
  }, [records])

  const handleClose = useCallback(
    async (record: TradeRecord, exitPrice: string) => {
      try {
        await api.closeTradeRecord(record.id, { exit_price: exitPrice })
        toast.success('已平仓')
        setClosingId(null)
        mutate()
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '平仓失败')
      }
    },
    [mutate],
  )

  const handleDelete = useCallback(
    async (record: TradeRecord) => {
      if (!confirm('确定删除这条记录？')) return
      try {
        await api.deleteTradeRecord(record.id)
        toast.success('已删除')
        mutate()
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '删除失败')
      }
    },
    [mutate],
  )

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-5 px-4 py-6">
        <section className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-3">
              <ShieldCheck size={20} className="mt-0.5 text-amber-300" />
              <div>
                <h1 className="text-base font-semibold text-white">模拟持仓已并入策略工作台</h1>
                <p className="mt-1 text-sm text-amber-100/80">这里保留兼容查看视图；新的生成和创建流程请从策略工作台进入。</p>
              </div>
            </div>
            <Link
              href="/strategies"
              className="inline-flex items-center justify-center rounded-lg bg-amber-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-amber-500"
            >
              前往策略工作台
            </Link>
          </div>
        </section>

        <section className="rounded-lg border border-slate-800 bg-surface p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-center gap-3">
              <Briefcase size={22} className="text-amber-400" />
              <div>
                <h2 className="text-xl font-bold text-white">模拟持仓</h2>
                <p className="mt-1 text-sm text-slate-400">记录虚拟交易，追踪盈亏表现</p>
              </div>
            </div>
          </div>

          {stats && (
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="已平仓盈亏" value={formatPrice(stats.totalPnl)} tone={stats.totalPnl >= 0 ? 'up' : 'down'} />
              <StatCard label="浮动盈亏" value={formatPrice(stats.openUnrealized)} tone={stats.openUnrealized >= 0 ? 'up' : 'down'} />
              <StatCard label="胜率" value={`${stats.winRate.toFixed(1)}%`} />
              <StatCard label="持仓 / 平仓" value={`${stats.openCount} / ${stats.closedCount}`} />
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2">
            {statusFilters.map((filter) => (
              <button
                key={filter.key}
                type="button"
                onClick={() => setStatusFilter(filter.key)}
                className={`rounded-full border px-3 py-1 text-xs transition ${
                  statusFilter === filter.key
                    ? 'border-amber-500/30 bg-amber-600/20 text-amber-300'
                    : 'border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </section>

        {error ? (
          <ErrorState message={error instanceof Error ? error.message : '加载失败'} onRetry={() => mutate()} />
        ) : isLoading ? (
          <PortfolioSkeleton />
        ) : !records || records.length === 0 ? (
          <EmptyState
            icon={BarChart3}
            title="暂无持仓"
            description={statusFilter === 'all' ? '还没有记录任何交易。' : '当前筛选条件下没有记录。'}
          />
        ) : (
          <section className="space-y-3">
            {records.map((record) => (
              <TradeCard
                key={record.id}
                record={record}
                isClosing={closingId === record.id}
                onStartClose={() => setClosingId(record.id)}
                onClose={(price) => handleClose(record, price)}
                onCancelClose={() => setClosingId(null)}
                onDelete={() => handleDelete(record)}
              />
            ))}
          </section>
        )}
      </div>
    </AppShell>
  )
}

function StatCard({ label, value, tone }: { label: string; value: string; tone?: 'up' | 'down' }) {
  const color = tone === 'up' ? 'text-red-400' : tone === 'down' ? 'text-green-400' : 'text-slate-200'
  return (
    <div className="rounded-lg border border-slate-800 bg-black/30 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-2 font-mono text-base font-semibold ${color}`}>{value}</div>
    </div>
  )
}

function TradeCard({
  record,
  isClosing,
  onStartClose,
  onClose,
  onCancelClose,
  onDelete,
}: {
  record: TradeRecord
  isClosing: boolean
  onStartClose: () => void
  onClose: (price: string) => void
  onCancelClose: () => void
  onDelete: () => void
}) {
  const [exitPrice, setExitPrice] = useState('')
  const isLong = record.direction === 'long'
  const pnl = record.status === 'open' ? record.unrealized_pnl : record.pnl
  const pnlNum = Number(pnl ?? 0)
  const pnlPercent = record.status === 'open' ? record.unrealized_pnl_percent : record.pnl_percent

  return (
    <div className="rounded-lg border border-slate-800 bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-white">{record.variety_symbol}</span>
            <span className="text-xs text-slate-500">{record.variety_name}</span>
            <span className={`rounded-full px-2 py-0.5 text-xs ${isLong ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'}`}>
              {isLong ? '做多' : '做空'} x {record.quantity}
            </span>
            {record.source === 'strategy' && (
              <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-300">
                策略生成
              </span>
            )}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
            <span>入场 {formatPrice(Number(record.entry_price))}</span>
            {record.exit_price && <span>出场 {formatPrice(Number(record.exit_price))}</span>}
            {record.stop_loss_price && <span>止损 {formatPrice(Number(record.stop_loss_price))}</span>}
            {record.take_profit_price && <span>止盈 {formatPrice(Number(record.take_profit_price))}</span>}
            <span className={`font-medium ${pnlNum >= 0 ? 'text-red-400' : 'text-green-400'}`}>
              {pnlNum >= 0 ? '+' : ''}
              {formatPrice(pnlNum)}
              {pnlPercent && ` (${pnlNum >= 0 ? '+' : ''}${Number(pnlPercent).toFixed(2)}%)`}
            </span>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-1">
          {record.status === 'open' && !isClosing && (
            <button
              type="button"
              onClick={onStartClose}
              className="rounded-md bg-amber-600/10 px-2 py-1 text-xs font-medium text-amber-400 transition hover:bg-amber-600/20"
            >
              平仓
            </button>
          )}
          <button
            type="button"
            onClick={onDelete}
            className="rounded p-1 text-slate-500 transition hover:bg-slate-800 hover:text-red-400"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {isClosing && (
        <div className="mt-3 flex gap-2">
          <input
            type="text"
            inputMode="decimal"
            value={exitPrice}
            onChange={(event) => setExitPrice(event.target.value)}
            placeholder="出场价格"
            className={`${inputClass} min-w-0 flex-1`}
          />
          <button
            type="button"
            onClick={() => onClose(exitPrice)}
            className="shrink-0 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-amber-500"
          >
            确认
          </button>
          <button
            type="button"
            onClick={onCancelClose}
            className="shrink-0 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500"
          >
            取消
          </button>
        </div>
      )}
    </div>
  )
}

function PortfolioSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="h-24 animate-pulse rounded-lg border border-slate-800 bg-surface p-4">
          <div className="flex items-start gap-3">
            <div className="h-6 w-16 rounded bg-slate-800" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-1/3 rounded bg-slate-800" />
              <div className="h-3 w-full rounded bg-slate-800" />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
