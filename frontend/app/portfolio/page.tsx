'use client'

import { useCallback, useMemo, useState } from 'react'
import AppShell from '@/components/layout/AppShell'
import ErrorState from '@/components/ui/ErrorState'
import EmptyState from '@/components/ui/EmptyState'
import { api, type TradeRecord } from '@/lib/api'
import { formatPrice } from '@/lib/format'
import {
  TrendingUp,
  TrendingDown,
  Plus,
  X,
  Trash2,
  Briefcase,
  BarChart3,
} from 'lucide-react'
import useSWR from 'swr'
import { toast } from 'sonner'

type PortfolioStatus = 'all' | 'open' | 'closed'

const statusFilters: { key: PortfolioStatus; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'open', label: '持仓中' },
  { key: 'closed', label: '已平仓' },
]

export default function PortfolioPage() {
  const [statusFilter, setStatusFilter] = useState<PortfolioStatus>('all')
  const [showCreateModal, setShowCreateModal] = useState(false)
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
    const closed = records.filter((r) => r.status === 'closed')
    const open = records.filter((r) => r.status === 'open')
    const totalPnl = closed.reduce((sum, r) => sum + (r.pnl ? Number(r.pnl) : 0), 0)
    const openUnrealized = open.reduce((sum, r) => sum + (r.unrealized_pnl ? Number(r.unrealized_pnl) : 0), 0)
    const winCount = closed.filter((r) => r.pnl && Number(r.pnl) > 0).length
    const winRate = closed.length > 0 ? (winCount / closed.length) * 100 : 0
    return { totalPnl, openUnrealized, winRate, closedCount: closed.length, openCount: open.length }
  }, [records])

  const handleCreate = useCallback(
    async (data: { variety_id: number; direction: 'long' | 'short'; entry_price: string; quantity: number }) => {
      try {
        await api.createTradeRecord(data)
        toast.success('持仓已创建')
        setShowCreateModal(false)
        mutate()
      } catch (e) {
        toast.error(e instanceof Error ? e.message : '创建失败')
      }
    },
    [mutate],
  )

  const handleClose = useCallback(
    async (id: number, exitPrice: string) => {
      try {
        await api.closeTradeRecord(id, { exit_price: exitPrice })
        toast.success('已平仓')
        setClosingId(null)
        mutate()
      } catch (e) {
        toast.error(e instanceof Error ? e.message : '平仓失败')
      }
    },
    [mutate],
  )

  const handleDelete = useCallback(
    async (id: number) => {
      if (!confirm('确定删除这条记录？')) return
      try {
        await api.deleteTradeRecord(id)
        toast.success('已删除')
        mutate()
      } catch (e) {
        toast.error(e instanceof Error ? e.message : '删除失败')
      }
    },
    [mutate],
  )

  return (
    <AppShell>
      <div className="mx-auto max-w-3xl space-y-5">
        {/* Header */}
        <section className="rounded-lg border border-slate-800 bg-surface p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-center gap-3">
              <Briefcase size={22} className="text-amber-400" />
              <div>
                <h1 className="text-xl font-bold text-white">模拟持仓</h1>
                <p className="mt-1 text-sm text-slate-400">记录虚拟交易，追踪盈亏表现</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setShowCreateModal(true)}
              className="inline-flex items-center gap-2 rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-amber-500"
            >
              <Plus size={16} />
              新建持仓
            </button>
          </div>

          {/* Stats */}
          {stats && (
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
              <StatCard label="总盈亏" value={formatPrice(stats.totalPnl)} tone={stats.totalPnl >= 0 ? 'up' : 'down'} />
              <StatCard label="浮动盈亏" value={formatPrice(stats.openUnrealized)} tone={stats.openUnrealized >= 0 ? 'up' : 'down'} />
              <StatCard label="胜率" value={`${stats.winRate.toFixed(1)}%`} />
              <StatCard label="持仓/平仓" value={`${stats.openCount} / ${stats.closedCount}`} />
            </div>
          )}

          {/* Status filters */}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {statusFilters.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setStatusFilter(f.key)}
                className={`rounded-full px-3 py-1 text-xs transition ${
                  statusFilter === f.key
                    ? 'bg-amber-600/20 text-amber-300 border border-amber-500/30'
                    : 'border border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                }`}
              >
                {f.label}
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
            description={statusFilter === 'all' ? '还没有记录任何交易，点击上方按钮创建第一条。' : '当前筛选条件下没有记录。'}
          />
        ) : (
          <section className="space-y-3">
            {records.map((record) => (
              <TradeCard
                key={record.id}
                record={record}
                isClosing={closingId === record.id}
                onStartClose={() => setClosingId(record.id)}
                onClose={(price) => handleClose(record.id, price)}
                onCancelClose={() => setClosingId(null)}
                onDelete={() => handleDelete(record.id)}
              />
            ))}
          </section>
        )}
      </div>

      {showCreateModal && (
        <CreateTradeModal onSubmit={handleCreate} onClose={() => setShowCreateModal(false)} />
      )}
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
  const pnlNum = pnl ? Number(pnl) : 0
  const pnlPercent = record.status === 'open' ? record.unrealized_pnl_percent : record.pnl_percent

  return (
    <div className="rounded-lg border border-slate-800 bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-white">{record.variety_symbol}</span>
            <span className="text-xs text-slate-500">{record.variety_name}</span>
            <span
              className={`ml-auto rounded-full px-2 py-0.5 text-xs ${
                isLong ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'
              }`}
            >
              {isLong ? '做多' : '做空'} × {record.quantity}
            </span>
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
            <span>入场 {formatPrice(Number(record.entry_price))}</span>
            {record.exit_price && <span>出场 {formatPrice(Number(record.exit_price))}</span>}
            <span
              className={`font-medium ${pnlNum >= 0 ? 'text-red-400' : 'text-green-400'}`}
            >
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
            onChange={(e) => setExitPrice(e.target.value)}
            placeholder="出场价格"
            className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-black/30 px-3 py-1.5 text-sm text-white placeholder-slate-500 outline-none transition focus:border-amber-500/50"
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

function CreateTradeModal({
  onSubmit,
  onClose,
}: {
  onSubmit: (data: { variety_id: number; direction: 'long' | 'short'; entry_price: string; quantity: number }) => void
  onClose: () => void
}) {
  const [form, setForm] = useState({
    variety_id: 0,
    direction: 'long' as 'long' | 'short',
    entry_price: '',
    quantity: 1,
  })
  const [submitting, setSubmitting] = useState(false)

  const { data: varieties } = useSWR('varieties-for-portfolio', () => api.getVarieties({ limit: 200 }), {
    revalidateOnFocus: false,
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const price = Number.parseFloat(form.entry_price)
    if (!Number.isFinite(price) || price <= 0) {
      toast.error('请输入有效的入场价格')
      return
    }
    if (form.variety_id <= 0) {
      toast.error('请选择品种')
      return
    }
    setSubmitting(true)
    await onSubmit(form)
    setSubmitting(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl border border-slate-700 bg-[#0f172a] shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <h2 className="text-base font-semibold text-white">新建模拟持仓</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 transition hover:bg-slate-800 hover:text-white"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 px-5 py-5">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">品种</label>
            <select
              value={form.variety_id}
              onChange={(e) => setForm({ ...form, variety_id: Number(e.target.value) })}
              className="w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white outline-none transition focus:border-amber-500/50"
            >
              <option value={0}>请选择品种</option>
              {varieties?.items.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.symbol} — {v.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">方向</label>
            <div className="flex gap-2">
              {(['long', 'short'] as const).map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setForm({ ...form, direction: d })}
                  className={`flex flex-1 items-center justify-center gap-2 rounded-lg border py-2 text-sm transition ${
                    form.direction === d
                      ? d === 'long'
                        ? 'border-red-500/30 bg-red-500/10 text-red-400'
                        : 'border-green-500/30 bg-green-500/10 text-green-400'
                      : 'border-slate-700 text-slate-400 hover:border-slate-500'
                  }`}
                >
                  {d === 'long' ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                  {d === 'long' ? '做多' : '做空'}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">入场价格</label>
              <input
                type="text"
                inputMode="decimal"
                value={form.entry_price}
                onChange={(e) => setForm({ ...form, entry_price: e.target.value })}
                placeholder="入场价"
                className="w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none transition focus:border-amber-500/50"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">手数</label>
              <input
                type="number"
                min={1}
                value={form.quantity}
                onChange={(e) => setForm({ ...form, quantity: Math.max(1, Number(e.target.value)) })}
                className="w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white outline-none transition focus:border-amber-500/50"
              />
            </div>
          </div>

          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300 transition hover:border-slate-500 hover:text-white"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-amber-500 disabled:opacity-50"
            >
              {submitting ? '保存中...' : '创建持仓'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function PortfolioSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-24 animate-pulse rounded-lg border border-slate-800 bg-surface p-4">
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
