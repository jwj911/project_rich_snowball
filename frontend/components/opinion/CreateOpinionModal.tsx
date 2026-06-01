'use client'

import { useState } from 'react'
import { X, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { toast } from 'sonner'
export type VarietyOption = {
  id: number
  symbol: string
  name: string
}

export type OpinionFormData = {
  variety_id: number
  type: 'long' | 'short' | 'neutral'
  reason: string
  target_price: string
  stop_loss: string
}

const opinionTypeConfig = {
  long: {
    label: '看多',
    icon: TrendingUp,
    color: 'text-red-400',
    bg: 'bg-red-500/10',
    border: 'border-red-500/30',
  },
  short: {
    label: '看空',
    icon: TrendingDown,
    color: 'text-green-400',
    bg: 'bg-green-500/10',
    border: 'border-green-500/30',
  },
  neutral: {
    label: '观望',
    icon: Minus,
    color: 'text-slate-400',
    bg: 'bg-slate-500/10',
    border: 'border-slate-500/30',
  },
} as const

export default function CreateOpinionModal({
  varieties,
  defaultVarietyId,
  readOnlyVariety = false,
  onSubmit,
  onClose,
}: {
  varieties: VarietyOption[]
  defaultVarietyId?: number
  readOnlyVariety?: boolean
  onSubmit: (data: OpinionFormData) => void | Promise<void>
  onClose: () => void
}) {
  const initialVarietyId = defaultVarietyId ?? varieties[0]?.id ?? 0
  const [form, setForm] = useState<OpinionFormData>({
    variety_id: initialVarietyId,
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
    try {
      await onSubmit(form)
    } finally {
      setSubmitting(false)
    }
  }

  const selectedVariety = varieties.find((v) => v.id === form.variety_id)

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
            {readOnlyVariety && selectedVariety ? (
              <div className="rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white">
                {selectedVariety.symbol} — {selectedVariety.name}
              </div>
            ) : (
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
            )}
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
