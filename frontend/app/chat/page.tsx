'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import AppShell from '@/components/layout/AppShell'
import { api } from '@/lib/api'
import type { ChatMessage, AgentTaskStepResponse } from '@/lib/api'
import {
  Send,
  Trash2,
  Bot,
  User,
  Sparkles,
  Loader2,
  Zap,
  Wrench,
  Brain,
  Database,
  ChevronDown,
  ChevronUp,
  TrendingUp,
  Shield,
  BarChart3,
  Search,
  Square,
} from 'lucide-react'
import FactorResultCard from '@/components/agent/FactorResultCard'
import TechAnalysisReportCard from '@/components/agent/TechAnalysisReportCard'
import StrategyResultCard from '@/components/agent/StrategyResultCard'
import BacktestResultCard from '@/components/agent/BacktestResultCard'
import { toast } from 'sonner'

type AgentModeKey = 'auto' | 'data' | 'backtest' | 'tech_analysis' | 'factor_mining' | 'risk_management'

interface AgentModeMeta {
  label: string
  icon: typeof Database
  desc: string
}

type AgentMessage = {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  agentMode?: AgentModeKey
  result?: Record<string, unknown>
  steps?: AgentTaskStepResponse[]
  isStreaming?: boolean
  created_at: string
}

const quickPrompts: Record<AgentModeKey, string[]> = {
  auto: [
    '帮我分析一下螺纹钢',
    '黄金目前适合做多还是做空',
    '螺纹钢5日上穿20日均线策略回测一下',
    '评估一下动量因子',
  ],
  data: [
    '螺纹钢最新价格是多少',
    '列出所有有色金属品种',
    '黄金近 20 日 K 线数据',
    '当前市场状态如何',
  ],
  backtest: [
    '螺纹钢 5 日上穿 20 日均线回测',
    '黄金 10 和 30 日均线策略回测',
    '铜 20 万资金 2 手均线回测',
    '原油做空 5/20 均线回测',
  ],
  tech_analysis: [
    '分析螺纹钢日线技术面',
    '黄金技术面如何？',
    '铜的走势技术判断',
    '原油期货技术分析',
  ],
  factor_mining: [
    '评估 "close / ts_delay(close, 5) - 1" 在黑色系的表现',
    '评估 "ts_rank(close, 20)" 在有色的表现',
    '评估螺纹钢动量因子',
    '评估 "ts_corr(close, volume, 10)" 在能源化工的表现',
  ],
  risk_management: [
    '螺纹钢做多风控方案',
    '黄金做空仓位怎么控制',
    '原油 5000 元做空风控',
    '铜的止损止盈怎么设',
  ],
}

const agentModes: Record<AgentModeKey, AgentModeMeta> = {
  auto: { label: '智能', icon: Sparkles, desc: '自动识别意图并路由到最佳 Agent' },
  data: { label: '数据', icon: Database, desc: '实时行情、品种信息、K 线查询' },
  backtest: { label: '回测', icon: BarChart3, desc: '口头策略解析、历史回测与评分' },
  tech_analysis: { label: '技术', icon: TrendingUp, desc: '经典指标综合技术面分析' },
  factor_mining: { label: '因子', icon: Search, desc: '因子 IC、分层回测、多空收益' },
  risk_management: { label: '风控', icon: Shield, desc: '仓位管理、止损止盈、回撤控制' },
}

export default function ChatPage() {
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(true)
  const [agentMode, setAgentMode] = useState<AgentModeKey>('auto')
  const bottomRef = useRef<HTMLDivElement>(null)
  const abortControllerRef = useRef<AbortController | null>(null)

  useEffect(() => {
    let cancelled = false
    api
      .getChatHistory({ limit: 100 })
      .then((history) => {
        if (!cancelled) {
          setMessages(
            history.map((m) => ({
              ...m,
              steps: undefined,
              isStreaming: false,
            })),
          )
        }
      })
      .catch(() => {
        if (!cancelled) toast.error('加载历史记录失败')
      })
      .finally(() => {
        if (!cancelled) setIsLoadingHistory(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleStop = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
      setIsLoading(false)
    }
  }, [])

  const handleSend = useCallback(
    async (text: string) => {
      if (!text.trim() || isLoading) return

      const mode = agentMode

      // 取消上一条未完成的流式请求
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
      const abortController = new AbortController()
      abortControllerRef.current = abortController

      const userMsg: AgentMessage = {
        id: Date.now(),
        role: 'user',
        content: text.trim(),
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, userMsg])
      setInput('')
      setIsLoading(true)

      // auto 模式：后端自动路由；用 agent_type=auto 走 SSE
      // 其余模式：直接走 Agent SSE
      const effectiveAgentType = mode

      // Agent 流式模式
      const assistantId = Date.now() + 1
      const assistantMsg: AgentMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        agentMode: mode,
        steps: [],
        isStreaming: true,
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, assistantMsg])

      try {
        await api.agentChatStream(
          { content: text.trim(), agent_type: effectiveAgentType },
          (event) => {
            setMessages((prev) => {
              const idx = prev.findIndex((m) => m.id === assistantId)
              if (idx === -1) return prev
              const updated = [...prev]
              const msg = { ...updated[idx] }

              if (event.event_type === 'start' || event.event_type === 'progress') {
                msg.content = (event.content as string) || msg.content || '正在处理...'
              } else if (event.event_type === 'thought') {
                msg.content = (event.content as string) || msg.content
              } else if (event.event_type === 'action') {
                msg.content = (event.content as string) || msg.content
              } else if (event.event_type === 'observation') {
                msg.content = (event.content as string) || msg.content
              } else if (event.event_type === 'result') {
                msg.content = (event.content as string) || msg.content
                msg.result = (event.result as Record<string, unknown>) || undefined
                msg.isStreaming = false
              } else if (event.event_type === 'error') {
                msg.content = (event.error_message as string) || '出错了'
                msg.isStreaming = false
              } else if (event.event_type === 'done') {
                msg.isStreaming = false
              }

              // 记录步骤
              if (event.step_number && event.role) {
                const steps = msg.steps || []
                const existing = steps.find((s) => s.step_number === event.step_number)
                if (!existing) {
                  steps.push({
                    id: event.step_number as number,
                    task_id: (event.task_id as number) || 0,
                    step_number: event.step_number as number,
                    role: event.role as string,
                    content: (event.content as string) || '',
                    tool_name: (event.tool_name as string) || null,
                    tool_input: (event.tool_input as Record<string, unknown>) || null,
                    tool_output: (event.tool_output as Record<string, unknown>) || null,
                    created_at: new Date().toISOString(),
                  })
                  steps.sort((a, b) => a.step_number - b.step_number)
                  msg.steps = steps
                }
              }

              updated[idx] = msg
              return updated
            })
          },
          {
            signal: abortController.signal,
            onMalformed: (raw) => {
              // eslint-disable-next-line no-console
              console.warn('Malformed SSE line:', raw)
            },
          },
        )
      } catch (e) {
        if (e instanceof Error && e.name === 'AbortError') {
          setMessages((prev) => {
            const idx = prev.findIndex((m) => m.id === assistantId)
            if (idx === -1) return prev
            const updated = [...prev]
            updated[idx] = {
              ...updated[idx],
              content: (updated[idx].content || '') + '\n\n[已取消]',
              isStreaming: false,
            }
            return updated
          })
        } else {
          toast.error(e instanceof Error ? e.message : 'Agent 请求失败')
          setMessages((prev) => {
            const idx = prev.findIndex((m) => m.id === assistantId)
            if (idx === -1) return prev
            const updated = [...prev]
            updated[idx] = {
              ...updated[idx],
              content: '请求失败，请稍后重试',
              isStreaming: false,
            }
            return updated
          })
        }
      } finally {
        setIsLoading(false)
        if (abortControllerRef.current === abortController) {
          abortControllerRef.current = null
        }
      }
    },
    [isLoading, agentMode],
  )

  const handleClear = useCallback(async () => {
    if (!confirm('确定清空所有对话记录？')) return
    try {
      await api.clearChatHistory()
      setMessages([])
      toast.success('对话已清空')
    } catch (e) {
      toast.error('清空失败')
    }
  }, [])

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend(input)
    }
  }

  const currentMode = agentModes[agentMode]

  return (
    <AppShell>
      <div className="mx-auto flex h-[calc(100vh-4rem)] max-w-3xl flex-col">
        {/* Header — horizontal mode bar */}
        <div className="flex items-center gap-2 border-b border-slate-800 px-4 py-2.5 overflow-x-auto">
          {(Object.keys(agentModes) as AgentModeKey[]).map((mode) => {
            const meta = agentModes[mode]
            const Icon = meta.icon
            const active = agentMode === mode
            return (
              <button
                key={mode}
                type="button"
                onClick={() => {
                  if (abortControllerRef.current) {
                    abortControllerRef.current.abort()
                    abortControllerRef.current = null
                    setIsLoading(false)
                  }
                  setAgentMode(mode)
                }}
                title={meta.desc}
                className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition ${
                  active
                    ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                    : 'border border-slate-700 text-slate-400 hover:text-slate-200 hover:border-slate-600'
                }`}
              >
                <Icon size={13} />
                {meta.label}
              </button>
            )
          })}
          {messages.length > 0 && (
            <button
              type="button"
              onClick={handleClear}
              className="ml-auto inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-400 transition hover:text-red-400"
            >
              <Trash2 size={12} />
              清空
            </button>
          )}
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {isLoadingHistory ? (
            <div className="flex h-full items-center justify-center">
              <Loader2 size={20} className="animate-spin text-slate-500" />
            </div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-6">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-amber-500/10">
                <Sparkles size={24} className="text-amber-400" />
              </div>
              <div className="text-center">
                <h2 className="text-lg font-semibold text-white">{currentMode.label} · Agent</h2>
                <p className="mt-1 text-sm text-slate-400">{currentMode.desc}</p>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                {quickPrompts[agentMode].map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => handleSend(prompt)}
                    className="rounded-full border border-slate-700 bg-surface px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              {messages.map((msg) => (
                <MessageBubble key={msg.id} message={msg} />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-slate-800 px-4 py-3">
          <div className="flex items-end gap-2 rounded-xl border border-slate-700 bg-surface p-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              placeholder={`输入问题，Shift+Enter 换行...`}
              className="max-h-32 min-h-10 flex-1 resize-none bg-transparent px-2 py-2 text-sm text-white placeholder-slate-500 outline-none"
            />
            {isLoading ? (
              <button
                type="button"
                onClick={handleStop}
                className="mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-red-600 text-white transition hover:bg-red-500"
                title="停止生成"
              >
                <Square size={14} fill="currentColor" />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => handleSend(input)}
                disabled={!input.trim()}
                className="mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-600 text-white transition hover:bg-amber-500 disabled:opacity-40"
              >
                <Send size={14} />
              </button>
            )}
          </div>
          <p className="mt-1.5 text-center text-[10px] text-slate-600">
            AI 回答仅供参考，不构成投资建议
            {agentMode === 'data' && ' · 数据查询会调用实时行情、品种数据库和K线数据'}
            {agentMode === 'backtest' && ' · 策略回测基于历史K线数据计算收益与评分，不构成投资建议'}
          </p>
        </div>
      </div>
    </AppShell>
  )
}

function MessageBubble({ message }: { message: AgentMessage }) {
  const isUser = message.role === 'user'
  const [showSteps, setShowSteps] = useState(false)
  const hasSteps = (message.steps?.length ?? 0) > 0
  const isFactorMining = message.agentMode === 'factor_mining'

  return (
    <div className={`flex items-start gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
          isUser ? 'bg-slate-700' : 'bg-amber-500/10'
        }`}
      >
        {isUser ? (
          <User size={14} className="text-slate-300" />
        ) : (
          <Bot size={14} className="text-amber-400" />
        )}
      </div>
      <div
        className={`max-w-[80%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? 'bg-amber-600 text-white'
            : 'border border-slate-800 bg-surface text-slate-200'
        }`}
      >
        <div className="whitespace-pre-wrap">
          {message.content || (message.isStreaming ? '正在分析...' : '')}
        </div>

        {isFactorMining && !message.isStreaming && (
          <FactorResultCard result={message.result?.data as Record<string, unknown>} steps={message.steps} />
        )}

        {message.agentMode === 'strategy_compiler' && !message.isStreaming && (
          <StrategyResultCard result={message.result?.data as Record<string, unknown>} />
        )}

        {message.agentMode === 'backtest' && !message.isStreaming && (
          <BacktestResultCard result={message.result?.data as Record<string, unknown>} />
        )}

        {message.agentMode === 'tech_analysis' && !message.isStreaming && (
          <TechAnalysisReportCard result={message.result?.data as Record<string, unknown>} />
        )}

        {message.isStreaming && (
          <div className="mt-2 flex items-center gap-1.5">
            <Loader2 size={12} className="animate-spin text-slate-400" />
            <span className="text-xs text-slate-400">正在处理...</span>
          </div>
        )}

        {hasSteps && !message.isStreaming && (
          <div className="mt-2">
            <button
              type="button"
              onClick={() => setShowSteps(!showSteps)}
              className="inline-flex items-center gap-1 text-xs text-slate-500 transition hover:text-amber-400"
            >
              <Wrench size={10} />
              {showSteps ? '隐藏执行过程' : '查看执行过程'}
              {showSteps ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
            </button>
            {showSteps && (
              <div className="mt-2 space-y-1.5 rounded-lg bg-slate-900/50 px-3 py-2">
                {message.steps?.map((step) => (
                  <StepItem key={step.step_number} step={step} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function StepItem({ step }: { step: AgentTaskStepResponse }) {
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
    system: Bot,
    error: Zap,
  }

  const Icon = roleIcons[step.role] || Bot
  const color = roleColors[step.role] || 'text-slate-400'
  const label = {
    thought: '思考',
    action: '调用工具',
    observation: '观察结果',
    system: '系统',
    error: '错误',
  }[step.role] || step.role

  return (
    <div className="flex items-start gap-2">
      <Icon size={12} className={`mt-0.5 shrink-0 ${color}`} />
      <div className="min-w-0">
        <div className={`text-[11px] font-medium ${color}`}>{label}</div>
        <div className="text-xs text-slate-400">{step.content}</div>
        {step.tool_name && (
          <div className="mt-0.5 text-[11px] text-slate-500">
            工具: {step.tool_name}
          </div>
        )}
      </div>
    </div>
  )
}
