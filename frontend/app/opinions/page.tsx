'use client'

import { useCallback, useMemo, useState } from 'react'
import AppShell from '@/components/layout/AppShell'
import ErrorState from '@/components/ui/ErrorState'
import EmptyState from '@/components/ui/EmptyState'
import { api, type Opinion, type Variety } from '@/lib/api'
import {
  PenLine,
  TrendingUp,
  TrendingDown,
  Minus,
  Target,
  Shield,
  Clock,
  Plus,
  X,
  ChevronDown,
  ChevronUp,
  Trash2,
  CheckCircle2,
  XCircle,
  AlertCircle,
} from 'lucide-react'
import useSWR from 'swr'
import { toast } from 'sonner'

type OpinionStatus = 'all' | 'open' | 'closed'
type OpinionFormData = {
  variety_id: number
  type: 'long' | 'short' | 'neutral'
  reason: string
  target_price: string
  stop_loss: string
}

const statusFilters: { key: OpinionStatus; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'open', label: '持仓中' },
  { key: 'closed', label: '已关闭' },
]

const opinionTypeConfig = {
  long: { label: '看多', icon: TrendingUp, color: 'text-red-400', bg: 'bg-red-500/10', border: 'border-red-500/30' },
  short: { label: '看空', icon: TrendingDown, color: 'text-green-400', bg: 'bg-green-500/10', border: 'border-green-500/30' },
  neutral: { label: '观望', icon: Minus, color: 'text-slate-400', bg: 'bg-slate-500/10', border: 'border-slate-500/30' },
}

const opinionStatusConfig: Record<string, { label: string; color: string; icon: typeof CheckCircle2 }> = {
  open: { label: '持仓中', color: 'text-amber-400', icon: AlertCircle },
  closed_profit: { label: '止盈关闭', color: 'text-red-400', icon: CheckCircle2 },
  closed_loss: { label: '止损关闭', color: 'text-green-400', icon: XCircle },
  expired: { label: '过期', color: 'text-slate-400', icon: Clock },
}

export default function OpinionsPage() {
  const [statusFilter, setStatusFilter] = useState<OpinionStatus>('all')
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [editingId, setEditingId] = useState<number | null>(null)

  const {
    data: opinions,
    error,
    isLoading,
    mutate,
  } = useSWR(
    ['my-opinions', statusFilter],
    () =>
      api.getMyOpinions({
        status: statusFilter === 'all' ? undefined : statusFilter,
        limit: 100,
      }),
    { revalidateOnFocus: false },
  )

  const { data: varieties } = useSWR('varieties-for-opinions', () => api.getVarieties({ limit: 200 }), {
    revalidateOnFocus: false,
  })

  const varietyMap = useMemo(() => {
    const map = new Map<number, Variety>()
    varieties?.items.forEach((v) => map.set(v.id, v))
    return map
  }, [varieties])

  const handleCreate = useCallback(
    async (data: OpinionFormData) => {
      try {
        await api.createOpinion({
          ...data,
          target_price: data.target_price || null,
          stop_loss: data.stop_loss || null,
        })
        toast.success('观点已创建')
        setShowCreateModal(false)
        mutate()
      } catch (e) {
        toast.error(e instanceof Error ? e.message : '创建失败')
      }
    },
    [mutate],
  )

  const handleClose = useCallback(
    async (id: number, outcome: 'profit' | 'loss' | 'breakeven') => {
      try {
        const statusMap: Record<string, string> = {
          profit: 'closed_profit',
          loss: 'closed_loss',
          breakeven: 'expired',
        }
        await api.updateOpinion(id, {
          status: statusMap[outcome] as Opinion['status'],
          actual_outcome: outcome,
        })
        toast.success('观点已关闭')
        mutate()
      } catch (e) {
        toast.error(e instanceof Error ? e.message : '关闭失败')
      }
    },
    [mutate],
  )

  const handleDelete = useCallback(
    async (id: number) => {
      if (!confirm('确定删除这条观点？')) return
      try {
        await api.deleteOpinion(id)
        toast.success('已删除')
        mutate()
      } catch (e) {
        toast.error(e instanceof Error ? e.message : '删除失败')
      }
    },
    [mutate],
  )

  const handleUpdateReason = useCallback(
    async (id: number, reason: string) => {
      try {
        await api.updateOpinion(id, { reason })
        toast.success('已更新')
        setEditingId(null)
        mutate()
      } catch (e) {
        toast.error(e instanceof Error ? e.message : '更新失败')
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
              <PenLine size={22} className="text-red-400" />
              <div>
                <h1 className="text-xl font-bold text-white">交易观点</h1>
                <p className="mt-1 text-sm text-slate-400">
                  记录你的交易决策与复盘
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setShowCreateModal(true)}
              className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-500"
            >
              <Plus size={16} />
              新建观点
            </button>
          </div>

          {/* Status filters */}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {statusFilters.map((f) => (
              <button
                key={f.key}
                type="button"
                onClick={() => setStatusFilter(f.key)}
                className={`rounded-full px-3 py-1 text-xs transition ${
                  statusFilter === f.key
                    ? 'bg-red-600/20 text-red-300 border border-red-500/30'
                    : 'border border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </section>

        {error ? (
          <ErrorState
            message={error instanceof Error ? error.message : '加载失败'}
            onRetry={() => mutate()}
          />
        ) : isLoading ? (
          <OpinionsSkeleton />
        ) : !opinions || opinions.length === 0 ? (
          <EmptyState
            icon={PenLine}
            title="暂无观点"
            description={
              statusFilter === 'all'
                ? '还没有记录任何交易观点，点击上方按钮创建第一条。'
                : '当前筛选条件下没有观点。'
            }
          />
        ) : (
          <section className="space-y-3">
            {opinions.map((opinion) => (
              <OpinionCard
                key={opinion.id}
                opinion={opinion}
                variety={varietyMap.get(opinion.variety_id)}
                isExpanded={expandedId === opinion.id}
                isEditing={editingId === opinion.id}
                onToggle={() => setExpandedId(expandedId === opinion.id ? null : opinion.id)}
                onStartEdit={() => setEditingId(opinion.id)}
                onUpdateReason={(reason) => handleUpdateReason(opinion.id, reason)}
                onClose={handleClose}
                onDelete={handleDelete}
              />
            ))}
          </section>
        )}
      </div>

      {showCreateModal && (
        <CreateOpinionModal
          varieties={varieties?.items ?? []}
          onSubmit={handleCreate}
          onClose={() => setShowCreateModal(false)}
        />
      )}
    </AppShell>
  )
}

function OpinionCard({
  opinion,
  variety,
  isExpanded,
  isEditing,
  onToggle,
  onStartEdit,
  onUpdateReason,
  onClose,
  onDelete,
}: {
  opinion: Opinion
  variety?: Variety
  isExpanded: boolean
  isEditing: boolean
  onToggle: () => void
  onStartEdit: () => void
  onUpdateReason: (reason: string) => void
  onClose: (id: number, outcome: 'profit' | 'loss' | 'breakeven') => void
  onDelete: (id: number) => void
}) {
  const [editReason, setEditReason] = useState(opinion.reason || '')
  const typeCfg = opinionTypeConfig[opinion.type] ?? opinionTypeConfig.neutral
  const statusCfg = opinionStatusConfig[opinion.status] ?? opinionStatusConfig.open
  const TypeIcon = typeCfg.icon
  const StatusIcon = statusCfg.icon

  return (
    <div className="rounded-lg border border-slate-800 bg-surface transition hover:border-slate-700">
      {/* Card header */}
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-start gap-3 p-4 text-left"
      >
        <div
          className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border ${typeCfg.bg} ${typeCfg.border}`}
        >
          <TypeIcon size={16} className={typeCfg.color} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-white">
              {variety?.symbol ?? opinion.variety_symbol}
            </span>
            <span className="text-xs text-slate-500">{variety?.name ?? opinion.variety_name}</span>
            <span className={`ml-auto flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${typeCfg.bg} ${typeCfg.color} border ${typeCfg.border}`}>
              {typeCfg.label}
            </span>
          </div>
          <p className="mt-1 text-sm text-slate-300 line-clamp-2">{opinion.reason}</p>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-xs text-slate-500">
            {opinion.target_price && (
              <span className="flex items-center gap-1">
                <Target size={12} className="text-slate-400" />
                目标 {opinion.target_price}
              </span>
            )}
            {opinion.stop_loss && (
              <span className="flex items-center gap-1">
                <Shield size={12} className="text-slate-400" />
                止损 {opinion.stop_loss}
              </span>
            )}
            <span className="flex items-center gap-1">
              <StatusIcon size={12} className={statusCfg.color} />
              <span className={statusCfg.color}>{statusCfg.label}</span>
            </span>
            <span className="flex items-center gap-1">
              <Clock size={12} />
              {formatRelativeTime(opinion.created_at)}
            </span>
          </div>
        </div>
        {isExpanded ? (
          <ChevronUp size={16} className="mt-1 shrink-0 text-slate-500" />
        ) : (
          <ChevronDown size={16} className="mt-1 shrink-0 text-slate-500" />
        )}
      </button>

      {/* Expanded actions */}
      {isExpanded && (
        <div className="border-t border-slate-800 px-4 pb-4 pt-3">
          {isEditing ? (
            <div className="space-y-3">
              <textarea
                value={editReason}
                onChange={(e) => setEditReason(e.target.value)}
                rows={3}
                className="w-full rounded-lg border border-slate-700 bg-black/30 p-3 text-sm text-white placeholder-slate-500 outline-none transition focus:border-red-500/50"
              />
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => onUpdateReason(editReason)}
                  className="rounded-lg bg-red-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-red-500"
                >
                  保存
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setEditReason(opinion.reason || '')
                    onStartEdit()
                  }}
                  className="rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500"
                >
                  取消
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                {opinion.status === 'open' && (
                  <>
                    <span className="text-xs text-slate-500">标记关闭：</span>
                    <button
                      type="button"
                      onClick={() => onClose(opinion.id, 'profit')}
                      className="inline-flex items-center gap-1 rounded-lg border border-red-700/40 bg-red-500/10 px-2.5 py-1 text-xs text-red-300 transition hover:bg-red-500/20"
                    >
                      <CheckCircle2 size={12} />
                      止盈
                    </button>
                    <button
                      type="button"
                      onClick={() => onClose(opinion.id, 'loss')}
                      className="inline-flex items-center gap-1 rounded-lg border border-green-700/40 bg-green-500/10 px-2.5 py-1 text-xs text-green-300 transition hover:bg-green-500/20"
                    >
                      <XCircle size={12} />
                      止损
                    </button>
                    <button
                      type="button"
                      onClick={() => onClose(opinion.id, 'breakeven')}
                      className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-500/10 px-2.5 py-1 text-xs text-slate-300 transition hover:bg-slate-500/20"
                    >
                      <Minus size={12} />
                      保本
                    </button>
                  </>
                )}
                <div className="ml-auto flex items-center gap-2">
                  <button
                    type="button"
                    onClick={onStartEdit}
                    className="text-xs text-slate-400 transition hover:text-white"
                  >
                    编辑
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(opinion.id)}
                    className="inline-flex items-center gap-1 text-xs text-slate-400 transition hover:text-red-400"
                  >
                    <Trash2 size={12} />
                    删除
                  </button>
                </div>
              </div>

              {opinion.actual_outcome && (
                <div className="rounded-lg bg-black/20 px-3 py-2 text-xs text-slate-400">
                  复盘结果：
                  <span
                    className={
                      opinion.actual_outcome === 'profit'
                        ? 'text-red-400'
                        : opinion.actual_outcome === 'loss'
                          ? 'text-green-400'
                          : 'text-slate-300'
                    }
                  >
                    {opinion.actual_outcome === 'profit'
                      ? '盈利'
                      : opinion.actual_outcome === 'loss'
                        ? '亏损'
                        : '保本'}
                  </span>
                  {opinion.closed_at && (
                    <span className="ml-2 text-slate-500">
                      关闭于 {formatRelativeTime(opinion.closed_at)}
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function CreateOpinionModal({
  varieties,
  onSubmit,
  onClose,
}: {
  varieties: Variety[]
  onSubmit: (data: OpinionFormData) => void
  onClose: () => void
}) {
  const [form, setForm] = useState<OpinionFormData>({
    variety_id: varieties[0]?.id ?? 0,
    type: 'long',
    reason: '',
    target_price: '',
    stop_loss: '',
  })
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.reason.trim()) {
      toast.error('请填写观点理由')
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
          <h2 className="text-base font-semibold text-white">新建交易观点</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 transition hover:bg-slate-800 hover:text-white"
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 px-5 py-5">
          {/* Variety */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">品种</label>
            <select
              value={form.variety_id}
              onChange={(e) => setForm({ ...form, variety_id: Number(e.target.value) })}
              className="w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white outline-none transition focus:border-red-500/50"
            >
              {varieties.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.symbol} — {v.name}
                </option>
              ))}
            </select>
          </div>

          {/* Type */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">方向</label>
            <div className="flex gap-2">
              {(['long', 'short', 'neutral'] as const).map((t) => {
                const cfg = opinionTypeConfig[t]
                const Icon = cfg.icon
                const active = form.type === t
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setForm({ ...form, type: t })}
                    className={`flex flex-1 items-center justify-center gap-2 rounded-lg border py-2 text-sm transition ${
                      active
                        ? `${cfg.bg} ${cfg.color} ${cfg.border}`
                        : 'border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                    }`}
                  >
                    <Icon size={14} />
                    {cfg.label}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Reason */}
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">理由</label>
            <textarea
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
              rows={4}
              placeholder="写下你的分析逻辑和决策依据..."
              className="w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none transition focus:border-red-500/50"
            />
          </div>

          {/* Target / Stop */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">目标价</label>
              <input
                type="text"
                inputMode="decimal"
                value={form.target_price}
                onChange={(e) => setForm({ ...form, target_price: e.target.value })}
                placeholder="可选"
                className="w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none transition focus:border-red-500/50"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-400">止损价</label>
              <input
                type="text"
                inputMode="decimal"
                value={form.stop_loss}
                onChange={(e) => setForm({ ...form, stop_loss: e.target.value })}
                placeholder="可选"
                className="w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none transition focus:border-red-500/50"
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
              className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-500 disabled:opacity-50"
            >
              {submitting ? '保存中...' : '创建观点'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function formatRelativeTime(iso: string): string {
  const date = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  if (diffHour < 24) return `${diffHour} 小时前`
  if (diffDay < 7) return `${diffDay} 天前`
  return date.toLocaleDateString('zh-CN')
}

function OpinionsSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="h-32 animate-pulse rounded-lg border border-slate-800 bg-surface p-4">
          <div className="flex items-start gap-3">
            <div className="h-8 w-8 shrink-0 rounded-lg bg-slate-800" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-1/3 rounded bg-slate-800" />
              <div className="h-3 w-full rounded bg-slate-800" />
              <div className="h-3 w-2/3 rounded bg-slate-800" />
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
