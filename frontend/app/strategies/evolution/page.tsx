'use client'

import { useState } from 'react'
import Link from 'next/link'
import useSWR from 'swr'
import { api } from '@/lib/api/client'
import AppShell from '@/components/layout/AppShell'
import type {
  EvolutionRunResponse,
  StrategyLifecycleResponse,
  DecayEvaluationResponse,
} from '@/lib/api/types'

const STATUS_MAP: Record<string, { label: string; cls: string }> = {
  completed:  { label: '已完成', cls: 'bg-emerald-900/50 text-emerald-400 border-emerald-700' },
  running:    { label: '运行中', cls: 'bg-amber-900/50 text-amber-400 border-amber-700' },
  failed:     { label: '失败',   cls: 'bg-red-900/50 text-red-400 border-red-700' },
  pending:    { label: '等待中', cls: 'bg-slate-700/50 text-slate-400 border-slate-600' },
  active:     { label: '活跃',   cls: 'bg-emerald-900/50 text-emerald-400 border-emerald-700' },
  paper_trading: { label: '模拟中', cls: 'bg-amber-900/50 text-amber-400 border-amber-700' },
  degraded:   { label: '已退化', cls: 'bg-orange-900/50 text-orange-400 border-orange-700' },
  retired:    { label: '已退役', cls: 'bg-red-900/50 text-red-400 border-red-700' },
}

const ACTION_LABELS: Record<string, string> = {
  keep: '保持',
  paper_trade: '模拟跟踪',
  re_optimize: '重新优化',
  retire: '退役',
}

export default function EvolutionPage() {
  const [tab, setTab] = useState<'runs' | 'lifecycle'>('runs')

  return (
    <AppShell>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-white">策略进化</h1>
          <div className="flex gap-1 rounded-lg bg-slate-800 p-1">
            {(['runs', 'lifecycle'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-md px-4 py-1.5 text-sm font-medium transition ${
                  tab === t
                    ? 'bg-amber-600 text-white shadow'
                    : 'text-slate-400 hover:text-white'
                }`}
              >
                {t === 'runs' ? '进化历史' : '策略生命周期'}
              </button>
            ))}
          </div>
        </div>

        {tab === 'runs' ? <EvolutionRunsTab /> : <LifecycleTab />}
      </div>
    </AppShell>
  )
}

/* ===================================================================
 * Tab 1: 进化运行历史
 * =================================================================== */

function EvolutionRunsTab() {
  const { data, error, isLoading } = useSWR('evolution-runs', () =>
    api.getEvolutionRuns({ limit: 30 })
  )

  if (isLoading) return <p className="text-sm text-slate-500">加载中...</p>
  if (error) return <p className="text-sm text-red-400">加载失败: {String(error)}</p>
  if (!data || data.items.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-700 p-12 text-center">
        <p className="text-slate-500">暂无进化运行记录</p>
        <p className="mt-2 text-xs text-slate-600">
          在 AI 对话中选择「策略进化」模式，触发一次进化后即可在此查看历史
        </p>
      </div>
    )
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {data.items.map((run) => (
        <RunCard key={run.id} run={run} />
      ))}
    </div>
  )
}

function RunCard({ run }: { run: EvolutionRunResponse }) {
  const [expanded, setExpanded] = useState(false)
  const st = STATUS_MAP[run.status] ?? { label: run.status, cls: 'bg-slate-700 text-slate-400 border-slate-600' }

  let summary: Record<string, unknown> | null = null
  try {
    summary = run.summary_json ? JSON.parse(run.summary_json) : null
  } catch { /* ignore */ }

  return (
    <div className="rounded-lg border border-slate-800 bg-surface p-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="font-mono text-sm font-semibold text-amber-400">{run.symbol}</span>
        <span className={`rounded-full border px-2 py-0.5 text-xs ${st.cls}`}>{st.label}</span>
      </div>
      <div className="space-y-1 text-xs text-slate-400">
        <div className="flex justify-between">
          <span>代数</span>
          <span className="text-white">{run.generations ?? '—'}</span>
        </div>
        <div className="flex justify-between">
          <span>种群大小</span>
          <span className="text-white">{run.population_size ?? '—'}</span>
        </div>
        {summary && (
          <>
            <div className="flex justify-between">
              <span>最优适应度</span>
              <span className="text-emerald-400">
                {typeof summary.final_best_fitness === 'number'
                  ? (summary.final_best_fitness as number).toFixed(1)
                  : '—'}
              </span>
            </div>
            {summary.early_stopped && (
              <div className="text-amber-500">⚠ 提前终止</div>
            )}
          </>
        )}
        {run.created_at && (
          <div className="pt-1 text-slate-600">
            {new Date(run.created_at).toLocaleString('zh-CN')}
          </div>
        )}
      </div>

      {run.best_strategy_id && (
        <Link
          href={`/strategies`}
          className="mt-3 inline-block text-xs text-amber-500 hover:text-amber-400 transition"
        >
          查看最优策略 →
        </Link>
      )}
    </div>
  )
}

/* ===================================================================
 * Tab 2: 策略生命周期
 * =================================================================== */

function LifecycleTab() {
  const { data, error, isLoading, mutate } = useSWR('lifecycles', () =>
    api.listLifecycles()
  )

  const [selected, setSelected] = useState<number[]>([])
  const [evaluating, setEvaluating] = useState(false)
  const [decayResults, setDecayResults] = useState<Record<number, DecayEvaluationResponse>>({})
  const [compareResult, setCompareResult] = useState<{
    items: import('@/lib/api/types').LifecycleComparisonItem[]
  } | null>(null)

  if (isLoading) return <p className="text-sm text-slate-500">加载中...</p>
  if (error) return <p className="text-sm text-red-400">加载失败: {String(error)}</p>
  if (!data || data.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-slate-700 p-12 text-center">
        <p className="text-slate-500">暂无策略生命周期记录</p>
        <p className="mt-2 text-xs text-slate-600">
          运行一次策略进化后，策略将自动注册到生命周期追踪中
        </p>
      </div>
    )
  }

  const toggleSelect = (id: number) => {
    setSelected((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const handleEvaluateAll = async () => {
    setEvaluating(true)
    const results: Record<number, DecayEvaluationResponse> = {}
    for (const lc of data) {
      try {
        const r = await api.evaluateDecay({ strategy_id: lc.strategy_id })
        results[lc.strategy_id] = r
      } catch { /* skip */ }
    }
    setDecayResults(results)
    setEvaluating(false)
    mutate()
  }

  const handleCompare = async () => {
    if (selected.length < 2) return
    try {
      const r = await api.compareLifecycles({ strategy_ids: selected })
      setCompareResult(r)
    } catch { /* skip */ }
  }

  return (
    <div className="space-y-4">
      {/* 操作栏 */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleEvaluateAll}
          disabled={evaluating}
          className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-500 transition disabled:opacity-50"
        >
          {evaluating ? '评估中...' : '评估全部衰减'}
        </button>
        {selected.length >= 2 && (
          <button
            onClick={handleCompare}
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm font-medium text-slate-300 hover:bg-slate-800 transition"
          >
            对比选中 ({selected.length})
          </button>
        )}
      </div>

      {/* 对比结果 */}
      {compareResult && (
        <div className="rounded-lg border border-slate-800 bg-surface p-4">
          <h3 className="mb-3 text-sm font-semibold text-white">策略对比</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-slate-700 text-left text-slate-400">
                  <th className="pb-2 pr-3">名称</th>
                  <th className="pb-2 pr-3">品种</th>
                  <th className="pb-2 pr-3">衰减分</th>
                  <th className="pb-2 pr-3">状态</th>
                  <th className="pb-2">推荐</th>
                </tr>
              </thead>
              <tbody>
                {compareResult.items.map((item) => (
                  <tr key={item.strategy_id} className="border-b border-slate-800">
                    <td className="py-2 pr-3 text-white">{item.strategy_name}</td>
                    <td className="py-2 pr-3 text-amber-400">{item.symbol}</td>
                    <td className="py-2 pr-3">
                      <span className={
                        (item.decay_score ?? 0) < 20 ? 'text-emerald-400' :
                        (item.decay_score ?? 0) < 40 ? 'text-amber-400' :
                        'text-red-400'
                      }>
                        {item.decay_score?.toFixed(1) ?? '—'}
                      </span>
                    </td>
                    <td className="py-2 pr-3">{STATUS_MAP[item.status]?.label ?? item.status}</td>
                    <td className="py-2">{ACTION_LABELS[item.recommended_action] ?? item.recommended_action}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button
            onClick={() => setCompareResult(null)}
            className="mt-3 text-xs text-slate-500 hover:text-white transition"
          >
            关闭对比
          </button>
        </div>
      )}

      {/* 生命周期列表 */}
      <div className="space-y-3">
        {data.map((lc) => {
          const decay = decayResults[lc.strategy_id]
          const st = STATUS_MAP[lc.status] ?? { label: lc.status, cls: 'bg-slate-700 text-slate-400 border-slate-600' }
          const isSelected = selected.includes(lc.strategy_id)

          return (
            <div
              key={lc.strategy_id}
              className={`rounded-lg border p-4 transition ${
                isSelected ? 'border-amber-600 bg-amber-950/20' : 'border-slate-800 bg-surface'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleSelect(lc.strategy_id)}
                    className="mt-0.5 accent-amber-600"
                  />
                  <div>
                    <div className="font-medium text-white">
                      策略 #{lc.strategy_id}
                      <span className="ml-2 text-xs text-slate-500">({lc.source})</span>
                    </div>
                    <div className="mt-1 text-xs text-slate-400">
                      衰减分: <span className={
                        (lc.decay_score ?? 0) < 20 ? 'text-emerald-400' :
                        (lc.decay_score ?? 0) < 40 ? 'text-amber-400' :
                        'text-red-400'
                      }>{lc.decay_score?.toFixed(1) ?? '—'}</span>
                      <span className="ml-3">更新: {lc.updated_at ? new Date(lc.updated_at).toLocaleString('zh-CN') : '—'}</span>
                    </div>
                  </div>
                </div>
                <span className={`rounded-full border px-2 py-0.5 text-xs ${st.cls}`}>{st.label}</span>
              </div>

              {decay && (
                <div className="mt-3 rounded-md bg-slate-900/50 p-3 text-xs">
                  <div className="flex flex-wrap gap-3">
                    <span>衰减: <span className="text-white">{decay.decay_score.toFixed(1)}</span></span>
                    <span>推荐: <span className="text-amber-400">{ACTION_LABELS[decay.recommended_action] ?? decay.recommended_action}</span></span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-slate-500">
                    {Object.entries(decay.details).map(([k, v]) => (
                      <span key={k}>{k}: {typeof v === 'number' ? v.toFixed(1) : String(v)}</span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
