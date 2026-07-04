'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import { api } from '@/lib/api'
import type { AgentTaskResponse } from '@/lib/api'
import { Loader2, Trash2, Bot } from 'lucide-react'
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
  const [loading, setLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<TaskStatus | 'all'>('all')

  const fetchTasks = async () => {
    setLoading(true)
    try {
      const params = statusFilter === 'all' ? undefined : { status: statusFilter }
      const data = await api.getAgentTasks(params)
      setTasks(data)
    } catch {
      toast.error('加载任务列表失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTasks()
  }, [statusFilter])

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
      <div className="mx-auto max-w-4xl px-4 py-6">
        <div className="mb-6 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10">
              <Bot size={20} className="text-amber-400" />
            </div>
            <div>
              <h1 className="text-lg font-semibold text-white">Agent 工作台</h1>
              <p className="text-sm text-slate-400">查看和管理你的 AI Agent 任务</p>
            </div>
          </div>

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

        {loading ? (
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
                <Link href={`/agents/${task.id}`} className="flex-1">
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
