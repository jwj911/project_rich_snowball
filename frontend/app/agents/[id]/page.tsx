'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import AppShell from '@/components/layout/AppShell'
import { api } from '@/lib/api'
import type { AgentTaskResponse, AgentTaskStepResponse } from '@/lib/api'
import { Loader2, ArrowLeft, Bot, Wrench, Brain, Zap, BotIcon } from 'lucide-react'
import { toast } from 'sonner'

const roleLabels: Record<string, string> = {
  thought: '思考',
  action: '调用工具',
  observation: '观察结果',
  system: '系统',
  error: '错误',
}

const roleColors: Record<string, string> = {
  thought: 'text-blue-400',
  action: 'text-amber-400',
  observation: 'text-green-400',
  system: 'text-slate-400',
  error: 'text-red-400',
}

const roleIcons: Record<string, typeof Brain> = {
  thought: Brain,
  action: Wrench,
  observation: Zap,
  system: BotIcon,
  error: Zap,
}

export default function AgentTaskDetailPage() {
  const params = useParams()
  const taskId = Number(params.id)
  const [task, setTask] = useState<AgentTaskResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!taskId) return
    api
      .getAgentTask(taskId)
      .then(setTask)
      .catch(() => toast.error('加载任务详情失败'))
      .finally(() => setLoading(false))
  }, [taskId])

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl px-4 py-6">
        <Link
          href="/agents"
          className="mb-4 inline-flex items-center gap-1 text-sm text-slate-400 transition hover:text-white"
        >
          <ArrowLeft size={16} /> 返回任务列表
        </Link>

        {loading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 size={24} className="animate-spin text-slate-500" />
          </div>
        ) : !task ? (
          <div className="text-center text-slate-400">任务不存在或无权查看</div>
        ) : (
          <div className="space-y-6">
            <div className="rounded-xl border border-slate-800 bg-surface p-5">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-amber-500/10">
                    <Bot size={20} className="text-amber-400" />
                  </div>
                  <div>
                    <div className="text-sm text-slate-400">{task.agent_type}</div>
                    <h1 className="text-lg font-semibold text-white">{task.query}</h1>
                  </div>
                </div>
                <span
                  className={`rounded-full px-3 py-1 text-xs ${
                    task.status === 'completed'
                      ? 'bg-green-600 text-white'
                      : task.status === 'failed'
                        ? 'bg-red-600 text-white'
                        : task.status === 'running'
                          ? 'bg-blue-600 text-white'
                          : 'bg-slate-600 text-slate-200'
                  }`}
                >
                  {task.status}
                </span>
              </div>

              {task.error_message && (
                <div className="mt-4 rounded-lg bg-red-500/10 p-3 text-sm text-red-400">
                  {task.error_message}
                </div>
              )}

              {typeof task.result?.answer === 'string' && (
                <div className="mt-4 whitespace-pre-wrap rounded-lg border border-slate-800 bg-slate-900/50 p-4 text-sm text-slate-200">
                  {task.result.answer}
                </div>
              )}
            </div>

            {task.sub_tasks && task.sub_tasks.length > 0 && (
              <div className="rounded-xl border border-slate-800 bg-surface p-5">
                <h2 className="mb-3 text-sm font-medium text-white">子任务</h2>
                <div className="space-y-2">
                  {task.sub_tasks.map((sub) => (
                    <Link
                      key={sub.id}
                      href={`/agents/${sub.id}`}
                      className="block rounded-lg border border-slate-800 bg-slate-900/50 p-3 transition hover:border-slate-700"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-white">{sub.query}</span>
                        <span className="text-xs text-slate-400">{sub.status}</span>
                      </div>
                      <div className="mt-1 text-xs text-slate-500">{sub.agent_type}</div>
                    </Link>
                  ))}
                </div>
              </div>
            )}

            <div className="rounded-xl border border-slate-800 bg-surface p-5">
              <h2 className="mb-3 text-sm font-medium text-white">执行步骤（{task.steps?.length ?? 0}）</h2>
              <div className="space-y-2">
                {(task.steps ?? []).map((step) => (
                  <StepItem key={step.id} step={step} />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  )
}

function StepItem({ step }: { step: AgentTaskStepResponse }) {
  const Icon = roleIcons[step.role] || Brain
  const color = roleColors[step.role] || 'text-slate-400'
  const label = roleLabels[step.role] || step.role

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/50 p-3">
      <div className="flex items-start gap-2">
        <Icon size={14} className={`mt-0.5 shrink-0 ${color}`} />
        <div className="min-w-0 flex-1">
          <div className={`text-xs font-medium ${color}`}>
            {label} #{step.step_number}
          </div>
          <div className="mt-0.5 text-sm text-slate-300">{step.content}</div>
          {step.tool_name && (
            <div className="mt-1 text-xs text-slate-500">工具: {step.tool_name}</div>
          )}
        </div>
      </div>
    </div>
  )
}
