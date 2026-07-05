'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ElementType, ReactNode } from 'react'
import useSWR from 'swr'
import AppShell from '@/components/layout/AppShell'
import { api } from '@/lib/api'
import type { AgentTaskResponse, BacktestResult, BacktestRunResponse, FactorResponse, StrategyPortfolioPlanResponse, StrategyResponse, TradeRecord } from '@/lib/api'
import { formatPrice } from '@/lib/format'
import {
  BarChart3,
  Briefcase,
  Code,
  Database,
  Loader2,
  Play,
  Plus,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react'
import { toast } from 'sonner'

type WorkspaceTab = 'library' | 'generate' | 'positions'
type PortfolioStatus = 'all' | 'open' | 'closed'
type RiskLevel = 'low' | 'medium' | 'high'

const tabs: Array<{ key: WorkspaceTab; label: string; icon: ElementType }> = [
  { key: 'library', label: '策略库', icon: BarChart3 },
  { key: 'generate', label: '生成持仓', icon: ShieldCheck },
  { key: 'positions', label: '持仓跟踪', icon: Briefcase },
]

const riskOptions: Array<{ key: RiskLevel; label: string; desc: string }> = [
  { key: 'low', label: '保守', desc: '单笔风险约 1%' },
  { key: 'medium', label: '均衡', desc: '单笔风险约 2%' },
  { key: 'high', label: '进取', desc: '单笔风险约 3%' },
]

const statusFilters: Array<{ key: PortfolioStatus; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'open', label: '持仓中' },
  { key: 'closed', label: '已平仓' },
]

const inputClass =
  'w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none transition focus:border-amber-500/50'

export default function StrategiesPage() {
  const [activeTab, setActiveTab] = useState<WorkspaceTab>('library')
  const [strategies, setStrategies] = useState<StrategyResponse[]>([])
  const [loading, setLoading] = useState(true)

  const loadStrategies = useCallback(async () => {
    setLoading(true)
    try {
      const rows = await api.getStrategies()
      setStrategies(rows)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载策略列表失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadStrategies()
  }, [loadStrategies])

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl px-4 py-6">
        <div className="mb-5 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">策略工作台</h1>
            <p className="mt-1 text-sm text-slate-400">从策略编译、风控生成到模拟持仓跟踪的一体化工作流</p>
          </div>
          <div className="flex rounded-lg border border-slate-800 bg-slate-950 p-1">
            {tabs.map((tab) => {
              const Icon = tab.icon
              return (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setActiveTab(tab.key)}
                  className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition ${
                    activeTab === tab.key
                      ? 'bg-amber-600 text-white'
                      : 'text-slate-400 hover:bg-slate-800 hover:text-slate-100'
                  }`}
                >
                  <Icon size={14} />
                  {tab.label}
                </button>
              )
            })}
          </div>
        </div>

        {activeTab === 'library' && (
          <StrategyLibrary strategies={strategies} loading={loading} onChanged={loadStrategies} />
        )}
        {activeTab === 'generate' && (
          <GeneratePositionPanel strategies={strategies} loading={loading} onCreated={() => setActiveTab('positions')} />
        )}
        {activeTab === 'positions' && <PortfolioTrackingPanel />}
      </div>
    </AppShell>
  )
}

function StrategyLibrary({
  strategies,
  loading,
  onChanged,
}: {
  strategies: StrategyResponse[]
  loading: boolean
  onChanged: () => Promise<void>
}) {
  const [showCreate, setShowCreate] = useState(false)
  const [createLoading, setCreateLoading] = useState(false)
  const [query, setQuery] = useState('')
  const [name, setName] = useState('')
  const [symbol, setSymbol] = useState('')
  const [backtestingId, setBacktestingId] = useState<number | null>(null)
  const [backtests, setBacktests] = useState<Record<number, BacktestRunResponse[]>>({})
  const [factors, setFactors] = useState<FactorResponse[]>([])
  const [factorsLoading, setFactorsLoading] = useState(true)
  const [factorSearch, setFactorSearch] = useState('')
  const [factorSymbol, setFactorSymbol] = useState('')
  const [factorDirection, setFactorDirection] = useState<'long' | 'short'>('long')
  const [factorSavingId, setFactorSavingId] = useState<number | null>(null)

  const loadFactors = useCallback(async () => {
    setFactorsLoading(true)
    try {
      const rows = await api.listFactors({ limit: 60 })
      setFactors(rows)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载因子列表失败')
    } finally {
      setFactorsLoading(false)
    }
  }, [])

  useEffect(() => {
    loadFactors()
  }, [loadFactors])

  const visibleFactors = useMemo(() => {
    const keyword = factorSearch.trim().toLowerCase()
    if (!keyword) return factors.slice(0, 12)
    return factors
      .filter((factor) =>
        [factor.name, factor.factor_id, factor.category, factor.source]
          .filter(Boolean)
          .some((value) => String(value).toLowerCase().includes(keyword)),
      )
      .slice(0, 12)
  }, [factorSearch, factors])

  const pollAgentTask = useCallback(async (taskId: number, maxAttempts = 30): Promise<AgentTaskResponse> => {
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const task = await api.getAgentTask(taskId)
      if (task.status === 'completed') {
        return task
      }
      if (task.status === 'failed') {
        throw new Error(task.error_message || '任务执行失败')
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1000))
    }
    throw new Error('策略编译超时，请稍后刷新查看')
  }, [])

  const handleCreate = useCallback(async () => {
    if (!name.trim() || !symbol.trim() || !query.trim()) {
      toast.error('请填写完整策略信息')
      return
    }
    setCreateLoading(true)
    try {
      const compileRes = await api.createAgentTask({ agent_type: 'strategy_compiler', query: `${symbol} ${query}` })
      const task = await pollAgentTask(compileRes.id)
      if (!task.result?.dsl) {
        toast.error('策略编译失败')
        return
      }
      const dsl = task.result.dsl as Record<string, unknown>
      await api.createStrategy({
        name: name.trim(),
        symbol: symbol.trim().toUpperCase(),
        dsl_json: JSON.stringify(dsl),
        timeframe: (dsl.timeframe as string) || '1d',
        direction: (dsl.direction as string) || 'long',
      })
      setShowCreate(false)
      setQuery('')
      setName('')
      setSymbol('')
      await onChanged()
      toast.success('策略创建成功')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建失败')
    } finally {
      setCreateLoading(false)
    }
  }, [name, symbol, query, onChanged, pollAgentTask])

  const handleDelete = useCallback(
    async (id: number) => {
      if (!confirm('确定删除该策略？')) return
      try {
        await api.deleteStrategy(id)
        await onChanged()
        toast.success('策略已删除')
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '删除失败')
      }
    },
    [onChanged],
  )

  const handleBacktest = useCallback(async (id: number) => {
    setBacktestingId(id)
    try {
      const run = await api.runStrategyBacktest(id, { initial_cash: 100000, quantity: 1, limit: 500 })
      setBacktests((prev) => ({ ...prev, [id]: [run, ...(prev[id] || [])] }))
      toast.success(`回测完成，评分 ${run.metrics_score ?? '-'} / 100`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '回测失败')
    } finally {
      setBacktestingId(null)
    }
  }, [])

  const loadBacktests = useCallback(async (id: number) => {
    try {
      const rows = await api.getStrategyBacktests(id)
      setBacktests((prev) => ({ ...prev, [id]: rows }))
    } catch {
      toast.error('加载回测历史失败')
    }
  }, [])

  const handleCreateFromFactor = useCallback(
    async (factor: FactorResponse) => {
      if (!factorSymbol.trim()) {
        toast.error('请先填写要应用的品种代码')
        return
      }
      setFactorSavingId(factor.id)
      try {
        await api.createStrategyFromFactor(factor.id, {
          symbol: factorSymbol.trim().toUpperCase(),
          direction: factorDirection,
          entry_value: 0,
          exit_value: 0,
        })
        await onChanged()
        toast.success('因子策略已加入策略库')
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '创建因子策略失败')
      } finally {
        setFactorSavingId(null)
      }
    },
    [factorDirection, factorSymbol, onChanged],
  )

  return (
    <section className="space-y-4">
      <div className="rounded-lg border border-slate-800 bg-surface p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-white">策略库</h2>
            <p className="mt-1 text-sm text-slate-400">保存自然语言编译后的策略，并用历史数据做基础验证</p>
          </div>
          <button
            type="button"
            onClick={() => setShowCreate((value) => !value)}
            className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-amber-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-amber-500"
          >
            <Plus size={15} />
            新建策略
          </button>
        </div>

        {showCreate && (
          <div className="mt-4 rounded-lg border border-slate-800 bg-slate-950/70 p-4">
            <div className="grid gap-3 lg:grid-cols-3">
              <Field label="策略名称">
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="如：螺纹钢均线交叉"
                  className={inputClass}
                />
              </Field>
              <Field label="品种代码">
                <input
                  value={symbol}
                  onChange={(event) => setSymbol(event.target.value)}
                  placeholder="如：RB"
                  className={inputClass}
                />
              </Field>
              <Field label="策略描述">
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="如：5 日均线上穿 20 日均线做多"
                  className={inputClass}
                />
              </Field>
            </div>
            <div className="mt-3 flex gap-2">
              <button
                type="button"
                onClick={handleCreate}
                disabled={createLoading}
                className="inline-flex items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-sm text-white transition hover:bg-amber-500 disabled:opacity-50"
              >
                {createLoading ? <Loader2 size={13} className="animate-spin" /> : <Code size={13} />}
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
      </div>

      <div className="rounded-lg border border-slate-800 bg-surface p-5">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-base font-semibold text-white">
              <Database size={16} className="text-amber-400" />
              因子策略
            </h2>
            <p className="mt-1 text-sm text-slate-400">从 factor_definitions 选择因子，一键保存为可回测策略</p>
          </div>
          <div className="grid gap-2 sm:grid-cols-[140px_120px_minmax(180px,1fr)]">
            <input
              value={factorSymbol}
              onChange={(event) => setFactorSymbol(event.target.value)}
              placeholder="品种，如 RB"
              className={inputClass}
            />
            <select
              value={factorDirection}
              onChange={(event) => setFactorDirection(event.target.value as 'long' | 'short')}
              className={inputClass}
            >
              <option value="long">做多</option>
              <option value="short">做空</option>
            </select>
            <div className="relative">
              <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
              <input
                value={factorSearch}
                onChange={(event) => setFactorSearch(event.target.value)}
                placeholder="搜索因子名称、ID、分类"
                className={`${inputClass} pl-8`}
              />
            </div>
          </div>
        </div>

        {factorsLoading ? (
          <div className="mt-4 flex h-24 items-center justify-center rounded-lg border border-slate-800 bg-slate-950/40">
            <Loader2 size={18} className="animate-spin text-slate-500" />
          </div>
        ) : visibleFactors.length === 0 ? (
          <div className="mt-4">
            <EmptyBlock icon={Database} title="暂无可用因子" description="factor_definitions 中没有匹配的活跃因子。" />
          </div>
        ) : (
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            {visibleFactors.map((factor) => (
              <div key={factor.id} className="rounded-lg border border-slate-800 bg-slate-950/50 p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="truncate text-sm font-semibold text-white">{factor.name}</h3>
                      <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
                        {factor.factor_id}
                      </span>
                      {factor.category && <span className="text-[10px] text-slate-500">{factor.category}</span>}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-2 text-[10px] text-slate-500">
                      <span>Q {formatFactorMetric(factor.q_score)}</span>
                      <span>RankICIR {formatFactorMetric(factor.test_rankicir)}</span>
                      <span>Sharpe {formatFactorMetric(factor.ls_sharpe)}</span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleCreateFromFactor(factor)}
                    disabled={factorSavingId === factor.id}
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-amber-500 disabled:opacity-50"
                  >
                    {factorSavingId === factor.id ? <Loader2 size={13} className="animate-spin" /> : <Sparkles size={13} />}
                    实现策略
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {loading ? (
        <LoadingBlock />
      ) : strategies.length === 0 ? (
        <EmptyBlock icon={BarChart3} title="暂无策略" description="先创建一个策略，再生成模拟持仓方案。" />
      ) : (
        <div className="space-y-3">
          {strategies.map((strategy) => (
            <StrategyCard
              key={strategy.id}
              strategy={strategy}
              onDelete={() => handleDelete(strategy.id)}
              onBacktest={() => handleBacktest(strategy.id)}
              backtesting={backtestingId === strategy.id}
              backtests={backtests[strategy.id] || []}
              onLoadBacktests={() => loadBacktests(strategy.id)}
            />
          ))}
        </div>
      )}
    </section>
  )
}

function GeneratePositionPanel({
  strategies,
  loading,
  onCreated,
}: {
  strategies: StrategyResponse[]
  loading: boolean
  onCreated: () => void
}) {
  const [strategyId, setStrategyId] = useState<number | ''>('')
  const [accountBalance, setAccountBalance] = useState('100000')
  const [riskLevel, setRiskLevel] = useState<RiskLevel>('medium')
  const [entryPrice, setEntryPrice] = useState('')
  const [plan, setPlan] = useState<StrategyPortfolioPlanResponse | null>(null)
  const [loadingPlan, setLoadingPlan] = useState(false)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    if (!strategyId && strategies.length > 0) setStrategyId(strategies[0].id)
  }, [strategies, strategyId])

  const selectedStrategy = useMemo(
    () => strategies.find((strategy) => strategy.id === strategyId) ?? null,
    [strategies, strategyId],
  )

  const handleGenerate = useCallback(async () => {
    if (!strategyId) {
      toast.error('请选择策略')
      return
    }
    setLoadingPlan(true)
    setPlan(null)
    try {
      const result = await api.generateStrategyPortfolioPlan(strategyId, {
        account_balance: accountBalance,
        risk_level: riskLevel,
        entry_price: entryPrice.trim() ? entryPrice.trim() : null,
      })
      setPlan(result)
      toast.success('持仓方案已生成')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '生成方案失败')
    } finally {
      setLoadingPlan(false)
    }
  }, [strategyId, accountBalance, riskLevel, entryPrice])

  const handleCreatePosition = useCallback(async () => {
    if (!plan) return
    if (!plan.can_create || plan.suggested_quantity < 1) {
      toast.error('建议手数小于 1 手，不能直接创建持仓')
      return
    }
    setCreating(true)
    try {
      await api.createTradeRecord({
        variety_id: plan.variety_id,
        strategy_id: plan.strategy_id,
        direction: plan.direction,
        entry_price: plan.entry_price,
        quantity: plan.suggested_quantity,
        account_balance: plan.account_balance,
        stop_loss_price: plan.stop_loss_price,
        take_profit_price: plan.take_profit_price,
        margin_required: plan.margin_required,
        risk_amount: plan.risk_amount,
        risk_reward_ratio: plan.risk_reward_ratio,
        source: 'strategy',
      })
      toast.success('模拟持仓已创建')
      onCreated()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建持仓失败')
    } finally {
      setCreating(false)
    }
  }, [plan, onCreated])

  if (loading) return <LoadingBlock />

  return (
    <section className="grid gap-4 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
      <div className="rounded-lg border border-slate-800 bg-surface p-5">
        <h2 className="text-base font-semibold text-white">生成持仓</h2>
        <p className="mt-1 text-sm text-slate-400">选择策略并输入账户可用金额，由规则风控生成入场、止损、止盈与建议手数。</p>

        {strategies.length === 0 ? (
          <div className="mt-6">
            <EmptyBlock icon={BarChart3} title="暂无可用策略" description="请先在策略库创建策略。" />
          </div>
        ) : (
          <div className="mt-4 space-y-4">
            <Field label="选择策略">
              <select
                value={strategyId}
                onChange={(event) => {
                  setStrategyId(Number(event.target.value))
                  setPlan(null)
                }}
                className={inputClass}
              >
                {strategies.map((strategy) => (
                  <option key={strategy.id} value={strategy.id}>
                    {strategy.name} · {strategy.symbol}
                  </option>
                ))}
              </select>
            </Field>

            {selectedStrategy && (
              <div className="rounded-lg border border-slate-800 bg-black/30 p-3 text-sm">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-white">{selectedStrategy.name}</span>
                  <DirectionBadge direction={selectedStrategy.direction} />
                  <span className="text-xs text-slate-500">{selectedStrategy.symbol}</span>
                </div>
                <p className="mt-1 line-clamp-2 text-xs text-slate-400">{readStrategyDescription(selectedStrategy)}</p>
              </div>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="账户可用金额">
                <input
                  value={accountBalance}
                  onChange={(event) => setAccountBalance(event.target.value)}
                  inputMode="decimal"
                  className={inputClass}
                />
              </Field>
              <Field label="入场价（可选）">
                <input
                  value={entryPrice}
                  onChange={(event) => setEntryPrice(event.target.value)}
                  inputMode="decimal"
                  placeholder="留空则使用实时行情"
                  className={inputClass}
                />
              </Field>
            </div>

            <div>
              <div className="mb-1.5 text-xs font-medium text-slate-400">风险偏好</div>
              <div className="grid gap-2 sm:grid-cols-3">
                {riskOptions.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    onClick={() => {
                      setRiskLevel(option.key)
                      setPlan(null)
                    }}
                    className={`rounded-lg border p-3 text-left transition ${
                      riskLevel === option.key
                        ? 'border-amber-500/50 bg-amber-500/10 text-amber-200'
                        : 'border-slate-800 bg-black/20 text-slate-300 hover:border-slate-600'
                    }`}
                  >
                    <div className="text-sm font-medium">{option.label}</div>
                    <div className="mt-1 text-xs text-slate-500">{option.desc}</div>
                  </button>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={handleGenerate}
              disabled={loadingPlan}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-amber-500 disabled:opacity-50"
            >
              {loadingPlan ? <Loader2 size={16} className="animate-spin" /> : <ShieldCheck size={16} />}
              生成风控持仓方案
            </button>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-slate-800 bg-surface p-5">
        <h2 className="text-base font-semibold text-white">方案预览</h2>
        {plan ? (
          <div className="mt-4 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-lg font-semibold text-white">{plan.variety_name}</span>
              <span className="text-sm text-slate-500">{plan.symbol}</span>
              <DirectionBadge direction={plan.direction} />
              <span className="rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-400">
                {riskOptions.find((item) => item.key === plan.risk_level)?.label ?? plan.risk_level}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 xl:grid-cols-3">
              <Metric label="入场价" value={formatPrice(Number(plan.entry_price))} />
              <Metric label="建议手数" value={`${plan.suggested_quantity} 手`} highlight={!plan.can_create ? 'down' : undefined} />
              <Metric label="账户金额" value={formatPrice(Number(plan.account_balance))} />
              <Metric label="止损价" value={formatPrice(Number(plan.stop_loss_price))} highlight="down" />
              <Metric label="止盈价" value={formatPrice(Number(plan.take_profit_price))} highlight="up" />
              <Metric label="风险收益比" value={`1:${Number(plan.risk_reward_ratio).toFixed(2)}`} />
              <Metric label="保证金占用" value={formatPrice(Number(plan.margin_required))} />
              <Metric label="单笔风险" value={formatPrice(Number(plan.risk_amount))} highlight="down" />
              <Metric label="建议原始手数" value={plan.suggested_lots.toFixed(2)} />
            </div>

            {plan.notes.length > 0 && (
              <div className="rounded-lg border border-slate-800 bg-black/30 p-3">
                <div className="mb-2 text-xs font-medium text-slate-400">风控说明</div>
                <ul className="space-y-1 text-xs text-slate-400">
                  {plan.notes.slice(0, 5).map((note, index) => (
                    <li key={`${note}-${index}`}>{note}</li>
                  ))}
                </ul>
              </div>
            )}

            <button
              type="button"
              onClick={handleCreatePosition}
              disabled={!plan.can_create || creating}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {creating ? <Loader2 size={16} className="animate-spin" /> : <Briefcase size={16} />}
              一键生成模拟持仓
            </button>
          </div>
        ) : (
          <div className="mt-6">
            <EmptyBlock icon={ShieldCheck} title="尚未生成方案" description="左侧选择策略和风险偏好后生成方案。" />
          </div>
        )}
      </div>
    </section>
  )
}

function PortfolioTrackingPanel() {
  const [statusFilter, setStatusFilter] = useState<PortfolioStatus>('all')
  const [closingId, setClosingId] = useState<number | null>(null)

  const {
    data: records,
    error,
    isLoading,
    mutate,
  } = useSWR(
    ['strategy-portfolio', statusFilter],
    () => api.getPortfolio({ status: statusFilter === 'all' ? undefined : statusFilter, limit: 100 }),
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
      if (!confirm('确定删除这条持仓记录？')) return
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
    <section className="space-y-4">
      <div className="rounded-lg border border-slate-800 bg-surface p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h2 className="text-base font-semibold text-white">持仓跟踪</h2>
            <p className="mt-1 text-sm text-slate-400">跟踪策略生成和手动创建的模拟持仓，实时计算浮动盈亏。</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {statusFilters.map((filter) => (
              <button
                key={filter.key}
                type="button"
                onClick={() => setStatusFilter(filter.key)}
                className={`rounded-full border px-3 py-1 text-xs transition ${
                  statusFilter === filter.key
                    ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                    : 'border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>

        {stats && (
          <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Metric label="已平仓盈亏" value={formatPrice(stats.totalPnl)} highlight={stats.totalPnl >= 0 ? 'up' : 'down'} />
            <Metric label="浮动盈亏" value={formatPrice(stats.openUnrealized)} highlight={stats.openUnrealized >= 0 ? 'up' : 'down'} />
            <Metric label="胜率" value={`${stats.winRate.toFixed(1)}%`} />
            <Metric label="持仓 / 平仓" value={`${stats.openCount} / ${stats.closedCount}`} />
          </div>
        )}
      </div>

      {error ? (
        <EmptyBlock icon={X} title="数据加载失败" description={error instanceof Error ? error.message : '请稍后重试'} />
      ) : isLoading ? (
        <LoadingBlock />
      ) : !records || records.length === 0 ? (
        <EmptyBlock icon={Briefcase} title="暂无持仓" description="可以先在“生成持仓”里创建第一条策略模拟持仓。" />
      ) : (
        <div className="space-y-3">
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
        </div>
      )}
    </section>
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
  const dsl = parseStrategyDsl(strategy)

  return (
    <div className="rounded-lg border border-slate-800 bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold text-white">{strategy.name}</h3>
            <DirectionBadge direction={strategy.direction} />
            <span className="text-xs text-slate-500">{fmtSymbol(strategy.symbol)}</span>
            {strategy.is_builtin && (
              <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-400">示例</span>
            )}
          </div>
          <p className="mt-1 line-clamp-2 text-xs text-slate-400">{readStrategyDescription(strategy)}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
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
            onClick={() => setExpanded((value) => !value)}
            className="rounded-md px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800"
          >
            {expanded ? '收起' : '展开'}
          </button>
          {!strategy.is_builtin && (
            <button
              type="button"
              onClick={onDelete}
              className="rounded-md p-1.5 text-slate-500 transition hover:bg-red-500/10 hover:text-red-400"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {expanded && dsl && (
        <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950/60 p-3">
          <div className="mb-2 text-xs font-medium text-amber-400">策略规则</div>
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-slate-300">
            {renderDslSummary(dsl)}
          </pre>
          <button
            type="button"
            onClick={() => {
              setShowBacktests((value) => !value)
              if (!showBacktests) onLoadBacktests()
            }}
            className="mt-2 inline-flex items-center gap-1 text-xs text-slate-500 transition hover:text-amber-400"
          >
            <BarChart3 size={11} />
            {showBacktests ? '隐藏回测历史' : '查看回测历史'}
          </button>
          {showBacktests && (
            <div className="mt-2 space-y-2">
              {backtests.length === 0 ? (
                <p className="text-xs text-slate-500">暂无回测记录</p>
              ) : (
                backtests.map((run) => <BacktestRunCard key={run.id} run={run} />)
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function BacktestRunCard({ run }: { run: BacktestRunResponse }) {
  const [expanded, setExpanded] = useState(false)
  const result = run.result
  const metrics = result?.metrics

  return (
    <div className="rounded border border-slate-800 bg-slate-950/40 p-2 text-xs">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={run.status === 'completed' ? 'text-green-400' : run.status === 'failed' ? 'text-red-400' : 'text-amber-400'}>
            {run.status}
          </span>
          {run.metrics_score !== null && <span className="text-slate-300">评分 {run.metrics_score}/100</span>}
          {metrics && (
            <span className="text-slate-500">
              收益 {Number(metrics.total_return_pct ?? 0).toFixed(2)}% / 回撤 {Number(metrics.max_drawdown_pct ?? 0).toFixed(2)}% / 交易 {run.trade_count ?? 0}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-slate-600">{run.created_at?.slice(0, 10)}</span>
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-slate-400 transition hover:text-amber-400"
          >
            {expanded ? '收起' : '详情'}
          </button>
        </div>
      </div>

      {expanded && result && (
        <div className="mt-3 space-y-3">
          <BacktestMetricsPanel metrics={metrics} />
          {result.equity_curve && result.equity_curve.length > 0 && (
            <EquityCurveChart data={result.equity_curve} />
          )}
          {result.signals && result.signals.length > 0 && (
            <BacktestSignalsList signals={result.signals} />
          )}
          {result.trades && result.trades.length > 0 && (
            <BacktestTradesList trades={result.trades} />
          )}
        </div>
      )}
    </div>
  )
}

function BacktestMetricsPanel({ metrics }: { metrics: BacktestResult['metrics'] | undefined }) {
  if (!metrics) return null
  const items = [
    { label: '总收益率', value: `${Number(metrics.total_return_pct ?? 0).toFixed(2)}%`, color: Number(metrics.total_return_pct ?? 0) >= 0 ? 'text-green-400' : 'text-red-400' },
    { label: '年化收益率', value: `${Number(metrics.annualized_return_pct ?? 0).toFixed(2)}%` },
    { label: '最大回撤', value: `${Number(metrics.max_drawdown_pct ?? 0).toFixed(2)}%`, color: 'text-red-400' },
    { label: '胜率', value: `${Number(metrics.win_rate_pct ?? 0).toFixed(2)}%` },
    { label: '盈亏比', value: Number(metrics.profit_loss_ratio ?? 0).toFixed(2) },
    { label: '夏普比率', value: Number(metrics.sharpe ?? 0).toFixed(2) },
    { label: '交易次数', value: Number(metrics.trade_count ?? 0) },
    { label: '评分', value: `${Number(metrics.score ?? 0)}/100` },
  ]
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {items.map((item) => (
        <div key={item.label} className="rounded bg-slate-900/60 p-2">
          <div className="text-[10px] text-slate-500">{item.label}</div>
          <div className={`text-sm font-medium ${item.color ?? 'text-slate-200'}`}>{item.value}</div>
        </div>
      ))}
    </div>
  )
}

function EquityCurveChart({ data }: { data: BacktestResult['equity_curve'] }) {
  const values = data.map((d) => d.equity)
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const width = 100
  const height = 40
  const points = data
    .map((d, i) => {
      const x = (i / (data.length - 1 || 1)) * width
      const y = height - ((d.equity - min) / range) * height
      return `${x},${y}`
    })
    .join(' ')
  const initial = data[0]?.equity ?? 0
  return (
    <div>
      <div className="mb-1 text-[10px] text-slate-500">资金曲线</div>
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full rounded bg-slate-900/60" preserveAspectRatio="none">
        <polyline fill="none" stroke="#f59e0b" strokeWidth="0.5" points={points} />
      </svg>
      <div className="mt-1 flex justify-between text-[10px] text-slate-500">
        <span>初始 {formatPrice(initial)}</span>
        <span>最终 {formatPrice(max)}</span>
      </div>
    </div>
  )
}

function BacktestSignalsList({ signals }: { signals: BacktestResult['signals'] }) {
  return (
    <div>
      <div className="mb-1 text-[10px] text-slate-500">买卖点 ({signals.length})</div>
      <div className="max-h-32 overflow-auto space-y-1">
        {signals.map((s, idx) => (
          <div key={idx} className="flex items-center justify-between rounded bg-slate-900/60 px-2 py-1">
            <span className={s.type === 'entry' ? 'text-green-400' : 'text-red-400'}>
              {s.type === 'entry' ? '买入' : '卖出'}
            </span>
            <span className="text-slate-400">{s.time?.slice(0, 10)}</span>
            <span className="text-slate-300">{formatPrice(Number(s.price))}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function BacktestTradesList({ trades }: { trades: BacktestResult['trades'] }) {
  return (
    <div>
      <div className="mb-1 text-[10px] text-slate-500">交易记录 ({trades.length})</div>
      <div className="max-h-40 overflow-auto space-y-1">
        {trades.map((t, idx) => (
          <div key={idx} className="flex items-center justify-between rounded bg-slate-900/60 px-2 py-1">
            <span className={t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>{t.pnl >= 0 ? '盈' : '亏'}</span>
            <span className="text-slate-500">{t.entry_time?.slice(0, 10)} → {t.exit_time?.slice(0, 10)}</span>
            <span className="text-slate-400">{t.entry_price} → {t.exit_price}</span>
            <span className={t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}>{t.pnl.toFixed(2)}</span>
          </div>
        ))}
      </div>
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
            <DirectionBadge direction={record.direction} />
            {record.source === 'strategy' && (
              <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-300">
                策略生成
              </span>
            )}
            <span className="rounded-full border border-slate-700 px-2 py-0.5 text-xs text-slate-400">x {record.quantity}</span>
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

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium text-slate-400">{label}</span>
      {children}
    </label>
  )
}

function Metric({ label, value, highlight }: { label: string; value: string; highlight?: 'up' | 'down' }) {
  const color = highlight === 'up' ? 'text-red-400' : highlight === 'down' ? 'text-green-400' : 'text-slate-100'
  return (
    <div className="rounded-lg border border-slate-800 bg-black/30 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-2 font-mono text-base font-semibold ${color}`}>{value}</div>
    </div>
  )
}

function DirectionBadge({ direction }: { direction: string }) {
  const isLong = direction === 'long'
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs ${isLong ? 'bg-red-500/10 text-red-400' : 'bg-green-500/10 text-green-400'}`}>
      {isLong ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
      {isLong ? '做多' : '做空'}
    </span>
  )
}

function EmptyBlock({ icon: Icon, title, description }: { icon: ElementType; title: string; description: string }) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center rounded-lg border border-slate-800 bg-surface p-6 text-center">
      <Icon size={28} className="text-slate-600" />
      <div className="mt-3 text-sm font-medium text-slate-300">{title}</div>
      <div className="mt-1 text-xs text-slate-500">{description}</div>
    </div>
  )
}

function LoadingBlock() {
  return (
    <div className="flex h-40 items-center justify-center rounded-lg border border-slate-800 bg-surface">
      <Loader2 size={20} className="animate-spin text-slate-500" />
    </div>
  )
}

function parseStrategyDsl(strategy: StrategyResponse): Record<string, unknown> | null {
  try {
    return JSON.parse(strategy.dsl_json) as Record<string, unknown>
  } catch {
    return null
  }
}

function readStrategyDescription(strategy: StrategyResponse): string {
  const dsl = parseStrategyDsl(strategy)
  if (dsl?.description && typeof dsl.description === 'string') return dsl.description
  return strategy.description || '暂无策略描述'
}

function formatFactorMetric(value: number | null): string {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-'
  return Number(value).toFixed(3)
}

// --- Symbol/indicator humanization (shared with StrategyResultCard) ---

const SYMBOL_NAMES: Record<string, string> = {
  rb: '螺纹钢', hc: '热卷', i: '铁矿石', j: '焦炭', jm: '焦煤',
  fg: '玻璃', sa: '纯碱', ma: '甲醇', ta: 'PTA', pp: '聚丙烯',
  l: '塑料', v: 'PVC', ru: '橡胶', sp: '纸浆', fu: '燃料油', bu: '沥青',
  sc: '原油', au: '黄金', ag: '白银', cu: '铜', al: '铝', zn: '锌', ni: '镍',
  si: '工业硅', lc: '碳酸锂', sr: '白糖', cf: '棉花', oi: '菜油',
  p: '棕榈油', y: '豆油', m: '豆粕', a: '黄豆一号', rm: '菜粕',
  c: '玉米', cs: '玉米淀粉', jd: '鸡蛋', lh: '生猪', ap: '苹果',
  eg: '乙二醇', eb: '苯乙烯', pg: '液化气', ur: '尿素',
}

function fmtSymbol(raw: string): string {
  return SYMBOL_NAMES[raw] || raw
}

const INDICATOR_NAMES: Record<string, string> = {
  sma: '均线', ema: '指数均线', rsi: 'RSI',
  macd_dif: 'MACD快线', macd_dea: 'MACD慢线', macd: 'MACD', macd_bar: 'MACD柱',
  boll_upper: '布林上轨', boll_mid: '布林中轨', boll_lower: '布林下轨',
  atr: 'ATR', kdj_k: 'KDJ-K', kdj_d: 'KDJ-D', kdj_j: 'KDJ-J', cci: 'CCI',
  close: '收盘价', volume: '成交量',
}

function fmtIndicator(raw: string): string {
  if (INDICATOR_NAMES[raw]) return INDICATOR_NAMES[raw]
  const m = raw.match(/^(sma|ema|rsi|cci)(\d+)$/)
  if (m) {
    if (m[1] === 'sma') return `${m[2]}日均线`
    if (m[1] === 'ema') return `${m[2]}日指数均线`
    return `${m[1].toUpperCase()}(${m[2]})`
  }
  return raw
}

const OPERATOR_NAMES: Record<string, string> = {
  cross_above: '上穿', cross_below: '下穿', above: '突破', below: '跌破',
  greater_than: '大于', less_than: '小于', equal: '等于', between: '介于',
}

function fmtDslCondition(cond: Record<string, unknown>): string {
  const ind = fmtIndicator(String(cond.indicator || ''))
  const op = OPERATOR_NAMES[String(cond.operator || '')] || cond.operator
  const ind2 = cond.indicator2 ? fmtIndicator(String(cond.indicator2)) : null
  const val = cond.value
  if (ind2) return `${ind} ${op} ${ind2}`
  if (val !== undefined) return `${ind} ${op} ${val}`
  return `${ind} ${op}`
}

function renderDslSummary(dsl: Record<string, unknown>): string {
  const lines: string[] = []
  const entry = dsl.entry as Record<string, unknown> | undefined
  const exit = dsl.exit as Record<string, unknown> | undefined
  const risk = dsl.risk as Record<string, unknown> | undefined

  if (entry?.conditions && Array.isArray(entry.conditions) && entry.conditions.length > 0) {
    const cs = entry.conditions.map((c) => fmtDslCondition(c as Record<string, unknown>)).join('，')
    lines.push('入场：' + cs)
  }
  if (exit?.conditions && Array.isArray(exit.conditions) && exit.conditions.length > 0) {
    const cs = exit.conditions.map((c) => fmtDslCondition(c as Record<string, unknown>)).join('，')
    lines.push('出场：' + cs)
  }
  if (risk) {
    const parts: string[] = []
    const pos = risk.position_size as Record<string, unknown> | undefined
    const sl = risk.stop_loss as Record<string, unknown> | undefined
    const tp = risk.take_profit as Record<string, unknown> | undefined
    if (pos) parts.push(`仓位：${pos.type}(${pos.value})`)
    if (sl) parts.push(`止损：${sl.type}(${sl.value})`)
    if (tp) parts.push(`止盈：${tp.type}(${tp.value})`)
    if (parts.length) lines.push('风控：' + parts.join('，'))
  }
  return lines.join('\n') || JSON.stringify(dsl).substring(0, 120)
}
