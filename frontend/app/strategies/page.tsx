'use client'

import { useCallback, useEffect, useState } from 'react'
import AppShell from '@/components/layout/AppShell'
import { api } from '@/lib/api'
import type { StrategyResponse, BacktestRunResponse } from '@/lib/api'
import {
  BarChart3,
  Code,
  Loader2,
  Play,
  Plus,
  Trash2,
} from 'lucide-react'
import { toast } from 'sonner'

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<StrategyResponse[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [createLoading, setCreateLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [name, setName] = useState('')
  const [symbol, setSymbol] = useState('')
  const [backtestingId, setBacktestingId] = useState<number | null>(null)
  const [backtests, setBacktests] = useState<Record<number, BacktestRunResponse[]>>({})

  useEffect(() => {
    api.getStrategies()
      .then(setStrategies)
      .catch(() => toast.error('加载策略列表失败'))
      .finally(() => setLoading(false))
  }, [])

  const handleCreate = useCallback(async () => {
    if (!name.trim() || !symbol.trim() || !query.trim()) {
      toast.error('请填写完整信息')
      return
    }
    setCreateLoading(true)
    try {
      const compileRes = await api.createAgentTask({ agent_type: 'strategy_compiler', query: `${symbol} ${query}` })
      const task = await api.getAgentTask(compileRes.id)
      if (task.status !== 'completed' || !task.result?.dsl) {
        toast.error('策略编译失败')
        return
      }
      const dsl = task.result.dsl as Record<string, unknown>
      const strategy = await api.createStrategy({
        name: name.trim(),
        symbol: symbol.trim().toUpperCase(),
        dsl_json: JSON.stringify(dsl),
        timeframe: (dsl.timeframe as string) || '1d',
        direction: (dsl.direction as string) || 'long',
      })
      setStrategies((prev) => [strategy, ...prev])
      setShowCreate(false)
      setQuery('')
      setName('')
      setSymbol('')
      toast.success('策略创建成功')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '创建失败')
    } finally {
      setCreateLoading(false)
    }
  }, [name, symbol, query])

  const handleDelete = useCallback(async (id: number) => {
    if (!confirm('确定删除该策略？')) return
    try {
      await api.deleteStrategy(id)
      setStrategies((prev) => prev.filter((s) => s.id !== id))
      toast.success('策略已删除')
    } catch (e) {
      toast.error('删除失败')
    }
  }, [])

  const handleBacktest = useCallback(async (id: number) => {
    setBacktestingId(id)
    try {
      const run = await api.runStrategyBacktest(id, { initial_cash: 100000, quantity: 1, limit: 500 })
      setBacktests((prev) => ({ ...prev, [id]: [run, ...(prev[id] || [])] }))
      toast.success(`回测完成，评分 ${run.metrics_score}/100`)
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '回测失败')
    } finally {
      setBacktestingId(null)
    }
  }, [])

  const loadBacktests = useCallback(async (id: number) => {
    try {
      const rows = await api.getStrategyBacktests(id)
      setBacktests((prev) => ({ ...prev, [id]: rows }))
    } catch (e) {
      // ignore
    }
  }, [])

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-4 py-6">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">策略工作台</h1>
            <p className="text-sm text-slate-400">编译自然语言策略，保存并回测验证</p>
          </div>
          <button
            type="button"
            onClick={() => setShowCreate(!showCreate)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-sm text-white transition hover:bg-amber-500"
          >
            <Plus size={14} />
            新建策略
          </button>
        </div>

        {showCreate && (
          <div className="mb-6 rounded-xl border border-slate-700 bg-slate-900/50 p-4">
            <h2 className="mb-3 text-sm font-semibold text-white">从自然语言创建策略</h2>
            <div className="grid gap-3 sm:grid-cols-3">
              <div>
                <label className="mb-1 block text-xs text-slate-400">策略名称</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="如：螺纹钢均线交叉策略"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-white outline-none focus:border-amber-500"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-400">品种代码</label>
                <input
                  value={symbol}
                  onChange={(e) => setSymbol(e.target.value)}
                  placeholder="如：RB"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-white outline-none focus:border-amber-500"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-400">策略描述</label>
                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="如：5日上穿20日均线做多"
                  className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-sm text-white outline-none focus:border-amber-500"
                />
              </div>
            </div>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={handleCreate}
                disabled={createLoading}
                className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-sm text-white transition hover:bg-amber-500 disabled:opacity-50"
              >
                {createLoading && <Loader2 size={12} className="animate-spin" />}
                <Code size={12} />
                编译并保存
              </button>
              <button
                type="button"
                onClick={() => setShowCreate(false)}
                className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-300 transition hover:bg-slate-800"
              >
                取消
              </button>
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex h-40 items-center justify-center">
            <Loader2 size={20} className="animate-spin text-slate-500" />
          </div>
        ) : strategies.length === 0 ? (
          <div className="flex h-40 flex-col items-center justify-center gap-2 text-slate-500">
            <BarChart3 size={32} />
            <p className="text-sm">暂无策略，点击上方按钮创建</p>
          </div>
        ) : (
          <div className="space-y-3">
            {strategies.map((s) => (
              <StrategyCard
                key={s.id}
                strategy={s}
                onDelete={() => handleDelete(s.id)}
                onBacktest={() => handleBacktest(s.id)}
                backtesting={backtestingId === s.id}
                backtests={backtests[s.id] || []}
                onLoadBacktests={() => loadBacktests(s.id)}
              />
            ))}
          </div>
        )}
      </div>
    </AppShell>
  )
}

function StrategyCard({
  strategy,
  onDelete,
  onBacktest,
  backtesting,
  backtests,
  onLoadBacktests,
}: {
  strategy: StrategyResponse
  onDelete: () => void
  onBacktest: () => void
  backtesting: boolean
  backtests: BacktestRunResponse[]
  onLoadBacktests: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [showBacktests, setShowBacktests] = useState(false)

  const dsl = (() => {
    try {
      return JSON.parse(strategy.dsl_json) as Record<string, unknown>
    } catch {
      return null
    }
  })()

  return (
    <div className="rounded-xl border border-slate-700 bg-slate-900/50 p-4">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-white">{strategy.name}</h3>
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${strategy.direction === 'long' ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'}`}>
              {strategy.direction === 'long' ? '做多' : '做空'}
            </span>
            <span className="text-[10px] text-slate-500">{strategy.symbol}</span>
          </div>
          <p className="mt-0.5 text-xs text-slate-400">
            {dsl ? (dsl.description as string) || strategy.description || '' : strategy.description || ''}
          </p>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onBacktest}
            disabled={backtesting}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-amber-400 transition hover:bg-amber-500/10 disabled:opacity-50"
          >
            {backtesting ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
            回测
          </button>
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="rounded-md px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800"
          >
            {expanded ? '收起' : '展开'}
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="rounded-md px-2 py-1 text-xs text-slate-500 transition hover:bg-red-500/10 hover:text-red-400"
          >
            <Trash2 size={12} />
          </button>
        </div>
      </div>

      {expanded && dsl && (
        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/50 p-3">
          <div className="mb-2 text-xs font-medium text-amber-400">DSL 规则</div>
          <pre className="max-h-48 overflow-auto text-xs text-slate-300">
            {JSON.stringify(dsl, null, 2)}
          </pre>
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              onClick={() => {
                setShowBacktests(!showBacktests)
                if (!showBacktests) onLoadBacktests()
              }}
              className="inline-flex items-center gap-1 text-xs text-slate-500 transition hover:text-amber-400"
            >
              <BarChart3 size={10} />
              {showBacktests ? '隐藏回测历史' : '查看回测历史'}
            </button>
          </div>
          {showBacktests && (
            <div className="mt-2 space-y-1">
              {backtests.length === 0 ? (
                <p className="text-xs text-slate-500">暂无回测记录</p>
              ) : (
                backtests.map((run) => (
                  <div key={run.id} className="flex items-center justify-between rounded border border-slate-800 px-2 py-1 text-xs">
                    <div className="flex items-center gap-2">
                      <span className={run.status === 'completed' ? 'text-green-400' : run.status === 'failed' ? 'text-red-400' : 'text-amber-400'}>
                        {run.status}
                      </span>
                      {run.metrics_score !== null && (
                        <span className="text-slate-300">评分 {run.metrics_score}/100</span>
                      )}
                    </div>
                    <div className="text-slate-500">{run.created_at?.slice(0, 10)}</div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
