'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import { api } from '@/lib/api'
import type { AgentPermissionHeartbeat, AgentStatusSummary, AgentTaskResponse } from '@/lib/api'
import {
  Activity,
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock3,
  Loader2,
  ShieldCheck,
  Trash2,
  XCircle,
} from 'lucide-react'
import { toast } from 'sonner'

type TaskStatus = 'pending' | 'running' | 'completed' | 'failed'

const statusLabels: Record<TaskStatus, string> = {
  pending: '待执行',
  running: '执行中',
  completed: '已完成',
  failed: '失败',
}

const statusColors: Record<TaskStatus, string> = {
  pending: 'bg-slate-600 text-slate-200',
  running: 'bg-blue-600 text-white',
  completed: 'bg-green-600 text-white',
  failed: 'bg-red-600 text-white',
}

const agentTypeLabels: Record<string, string> = {
  data: '数据助手',
  tech_analysis: '技术分析',
  risk_management: '风控管理',
  analysis_pipeline: '完整分析',
  factor_mining: '因子评估',
  backtest: '策略回测',
  orchestrator: '编排器',
  strategy_compiler: '策略编译',
}

export default function AgentsPage() {
  const [tasks, setTasks] = useState<AgentTaskResponse[]>([])
  const [tasksLoading, setTasksLoading] = useState(true)
  const [statusLoading, setStatusLoading] = useState(true)
  const [agentStatus, setAgentStatus] = useState<AgentStatusSummary | null>(null)
  const [heartbeat, setHeartbeat] = useState<AgentPermissionHeartbeat | null>(null)
  const [heartbeatError, setHeartbeatError] = useState(false)
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all')

  const fetchTasks = useCallback(async () => {
    setTasksLoading(true)
    try {
      const params = statusFilter === 'all' ? undefined : { status: statusFilter }
      const data = await api.getAgentTasks(params)
      setTasks(data)
    } catch {
      toast.error('加载任务列表失败')
    } finally {
      setTasksLoading(false)
    }
  }, [statusFilter])

  const fetchWorkspaceStatus = useCallback(async () => {
    setStatusLoading(true)
    const [statusResult, heartbeatResult] = await Promise.allSettled([
      api.getAgentStatus(),
      api.getAgentPermissionHeartbeat(),
    ])

    if (statusResult.status === 'fulfilled') {
      setAgentStatus(statusResult.value)
    } else {
      toast.error('加载 Agent 状态失败')
    }

    if (heartbeatResult.status === 'fulfilled') {
      setHeartbeat(heartbeatResult.value)
      setHeartbeatError(false)
    } else {
      setHeartbeat(null)
      setHeartbeatError(true)
    }

    setStatusLoading(false)
  }, [])

  useEffect(() => {
    fetchTasks()
  }, [fetchTasks])

  useEffect(() => {
    fetchWorkspaceStatus()
    const timer = window.setInterval(fetchWorkspaceStatus, 30000)
    return () => window.clearInterval(timer)
  }, [fetchWorkspaceStatus])

  const visibleCapabilities = useMemo(
    () => (agentStatus?.capabilities ?? []).filter((item) => item.agent_type !== 'orchestrator'),
    [agentStatus],
  )

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除该任务？')) return
    try {
      await api.deleteAgentTask(id)
      setTasks((prev) => prev.filter((t) => t.id !== id))
      toast.success('任务已删除')
    } catch {
      toast.error('删除失败')
    }
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-5xl px-4 py-6">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10">
              <Bot size={20} className="text-amber-400" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-white">Agent 工作台</h1>
              <p className="text-sm text-slate-400">查看 Agent 能力、权限状态和任务执行记录</p>
            </div>
          </div>
        </div>

        <div className="mb-6 space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="全部任务" value={agentStatus?.total_tasks ?? 0} loading={statusLoading} />
            <Metric label="运行中" value={agentStatus?.running_tasks ?? 0} tone="blue" loading={statusLoading} />
            <Metric label="已完成" value={agentStatus?.completed_tasks ?? 0} tone="green" loading={statusLoading} />
            <Metric label="失败" value={agentStatus?.failed_tasks ?? 0} tone="red" loading={statusLoading} />
          </div>

          <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
            <section className="rounded-lg border border-slate-800 bg-surface p-4">
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm font-medium text-white">
                  <Activity size={16} className="text-blue-400" />
                  Agent 能力
                </div>
                {agentStatus && (
                  <span className="text-xs text-slate-500">
                    {new Date(agentStatus.server_time).toLocaleTimeString('zh-CN')}
                  </span>
                )}
              </div>

              {statusLoading && visibleCapabilities.length === 0 ? (
                <div className="flex h-24 items-center justify-center">
                  <Loader2 size={18} className="animate-spin text-slate-500" />
                </div>
              ) : (
                <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                  {visibleCapabilities.map((item) => (
                    <div key={item.agent_type} className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0">
                          <div className="truncate text-sm font-medium text-white">{item.label}</div>
                          <div className="mt-0.5 truncate text-xs text-slate-500">{item.agent_type}</div>
                        </div>
                        {item.enabled ? (
                          <CheckCircle2 size={17} className="shrink-0 text-green-400" />
                        ) : (
                          <XCircle size={17} className="shrink-0 text-red-400" />
                        )}
                      </div>
                      <div className="mt-2 text-xs text-slate-400">
                        {item.enabled ? '可用' : item.reason || '暂不可用'}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="rounded-lg border border-slate-800 bg-surface p-4">
              <div className="mb-3 flex items-center gap-2 text-sm font-medium text-white">
                <ShieldCheck size={16} className={heartbeatError ? 'text-red-400' : 'text-green-400'} />
                权限心跳
              </div>
              {heartbeatError ? (
                <div className="rounded-lg bg-red-500/10 p-3 text-sm text-red-300">
                  登录态异常或权限检查失败
                </div>
              ) : heartbeat ? (
                <div className="space-y-3">
                  <div className="flex items-center gap-2 text-sm text-green-400">
                    <CheckCircle2 size={16} />
                    权限正常
                  </div>
                  <div className="grid gap-2 text-xs">
                    <Info label="用户" value={`${heartbeat.username} (#${heartbeat.user_id})`} />
                    <Info label="角色" value={heartbeat.role} />
                    <Info label="可用 Agent" value={`${heartbeat.allowed_agent_types.length} 个`} />
                    <Info label="检查时间" value={new Date(heartbeat.server_time).toLocaleTimeString('zh-CN')} />
                  </div>
                </div>
              ) : (
                <div className="flex h-24 items-center justify-center">
                  <Loader2 size={18} className="animate-spin text-slate-500" />
                </div>
              )}
            </section>
          </div>

          {agentStatus?.capabilities.some((item) => !item.enabled) && (
            <div className="flex items-center gap-2 rounded-lg border border-amber-500/20 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
              <AlertTriangle size={16} />
              部分 Agent 暂不可用，请查看能力卡片中的原因。
            </div>
          )}
        </div>

        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-medium text-white">任务记录</h2>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as TaskStatus | 'all')}
            className="rounded-lg border border-slate-700 bg-surface px-3 py-1.5 text-sm text-white outline-none focus:border-amber-500"
          >
            <option value="all">全部状态</option>
            <option value="pending">待执行</option>
            <option value="running">执行中</option>
            <option value="completed">已完成</option>
            <option value="failed">失败</option>
          </select>
        </div>

        {tasksLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 size={24} className="animate-spin text-slate-500" />
          </div>
        ) : tasks.length === 0 ? (
          <div className="rounded-xl border border-dashed border-slate-700 p-12 text-center">
            <p className="text-slate-400">暂无任务，去 <Link href="/chat" className="text-amber-400 hover:underline">AI 助手</Link> 创建吧</p>
          </div>
        ) : (
          <div className="space-y-3">
            {tasks.map((task) => (
              <div
                key={task.id}
                className="flex items-center justify-between rounded-xl border border-slate-800 bg-surface p-4 transition hover:border-slate-700"
              >
                <Link href={`/agents/detail?id=${task.id}`} className="flex-1">
                  <div className="flex items-center gap-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs ${statusColors[task.status as TaskStatus] || 'bg-slate-600 text-slate-200'}`}
                    >
                      {statusLabels[task.status as TaskStatus] || task.status}
                    </span>
                    <span className="text-xs text-slate-400">
                      {agentTypeLabels[task.agent_type] || task.agent_type}
                    </span>
                  </div>
                  <div className="mt-1 text-sm text-white">{task.query}</div>
                  <div className="mt-1 text-xs text-slate-500">
                    {new Date(task.created_at).toLocaleString('zh-CN')}
                  </div>
                </Link>

                <button
                  type="button"
                  onClick={() => handleDelete(task.id)}
                  className="ml-4 rounded-lg p-2 text-slate-500 transition hover:bg-slate-800 hover:text-red-400"
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </AppShell>
  )
}

function Metric({
  label,
  value,
  tone = 'slate',
  loading,
}: {
  label: string
  value: number
  tone?: 'slate' | 'blue' | 'green' | 'red'
  loading?: boolean
}) {
  const colors = {
    slate: 'text-white',
    blue: 'text-blue-400',
    green: 'text-green-400',
    red: 'text-red-400',
  }
  return (
    <div className="rounded-lg border border-slate-800 bg-surface p-4">
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Clock3 size={13} />
        {label}
      </div>
      <div className={`mt-2 text-2xl font-semibold ${colors[tone]}`}>
        {loading ? <Loader2 size={18} className="animate-spin text-slate-500" /> : value}
      </div>
    </div>
  )
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-900/50 px-2.5 py-2">
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className="mt-0.5 truncate text-xs text-slate-200">{value}</div>
    </div>
  )
}
