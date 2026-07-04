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
  Workflow,
  Search,
} from 'lucide-react'
import FactorResultCard from '@/components/agent/FactorResultCard'
import TechAnalysisReportCard from '@/components/agent/TechAnalysisReportCard'
import { toast } from 'sonner'

type AgentMode = 'chat' | 'data' | 'tech_analysis' | 'risk_management' | 'analysis_pipeline' | 'factor_mining' | 'backtest'

interface AgentMessage {
  id: number
  role: 'user' | 'assistant' | 'system'
  content: string
  agentMode?: AgentMode
  result?: Record<string, unknown>
  steps?: AgentTaskStepResponse[]
  isStreaming?: boolean
  created_at: string
}

const quickPrompts: Record<AgentMode, string[]> = {
  chat: [
    '分析一下螺纹钢最近的走势',
    '黄金目前适合做多还是做空？',
    '帮我总结今天的热门品种',
    '原油期货有什么新闻？',
  ],
  data: [
    '螺纹钢最新价格是多少',
    '列出所有有色金属品种',
    '黄金近 20 日 K 线数据',
    '当前市场状态如何',
  ],
  tech_analysis: [
    '分析螺纹钢日线技术面',
    '黄金技术面如何？',
    '铜的走势技术判断',
    '原油期货技术分析',
  ],
  risk_management: [
    '螺纹钢做多风控方案',
    '黄金做空仓位怎么控制',
    '原油 5000 元做空风控',
    '铜的止损止盈怎么设',
  ],
  analysis_pipeline: [
    '帮我完整分析螺纹钢',
    '给出黄金的完整分析与风控方案',
    '分析原油并提供风控建议',
    '铜的多头完整分析',
  ],
  factor_mining: [
    '评估 "close / ts_delay(close, 5) - 1" 在黑色系的表现',
    '评估 "ts_rank(close, 20) / ts_rank(volume, 20)" 在有色的表现',
    '评估螺纹钢动量因子',
    '评估 "ts_corr(close, volume, 10)" 在能源化工的表现',
  ],
  backtest: [
    '螺纹钢 5 日上穿 20 日均线回测',
    '黄金 10 和 30 日均线策略回测',
    '铜 20 万资金 2 手均线回测',
    '原油做空 5/20 均线回测',
  ],
}

const modeLabels: Record<AgentMode, { label: string; icon: typeof Database; desc: string }> = {
  chat: { label: 'AI 助手', icon: Sparkles, desc: '期货行情分析、投资知识问答' },
  data: { label: '数据助手', icon: Database, desc: '实时行情、品种信息、K 线数据查询' },
  tech_analysis: { label: '技术分析', icon: TrendingUp, desc: '基于经典指标的综合技术面分析' },
  risk_management: { label: '风控管理', icon: Shield, desc: '仓位管理、止损止盈、回撤控制' },
  analysis_pipeline: { label: '完整分析', icon: Workflow, desc: '数据 + 技术分析 + 风控方案自动串联' },
  factor_mining: { label: '因子评估', icon: Search, desc: '评估用户给定因子的 IC、分层回测与回撤' },
  backtest: { label: '策略回测', icon: BarChart3, desc: '口头策略解析、历史回测与策略评分' },
}

export default function ChatPage() {
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(true)
  const [agentMode, setAgentMode] = useState<AgentMode>('chat')
  const [showModeMenu, setShowModeMenu] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)
  const modeMenuRef = useRef<HTMLDivElement>(null)

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

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (modeMenuRef.current && !modeMenuRef.current.contains(e.target as Node)) {
        setShowModeMenu(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleSend = useCallback(
    async (text: string) => {
      if (!text.trim() || isLoading) return

      const userMsg: AgentMessage = {
        id: Date.now(),
        role: 'user',
        content: text.trim(),
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, userMsg])
      setInput('')
      setIsLoading(true)

      if (agentMode === 'data' || agentMode === 'tech_analysis' || agentMode === 'risk_management' || agentMode === 'analysis_pipeline' || agentMode === 'factor_mining' || agentMode === 'backtest') {
        // Agent 流式模式
        const assistantId = Date.now() + 1
        const assistantMsg: AgentMessage = {
          id: assistantId,
          role: 'assistant',
          content: '',
          agentMode,
          steps: [],
          isStreaming: true,
          created_at: new Date().toISOString(),
        }
        setMessages((prev) => [...prev, assistantMsg])

        try {
          await api.agentChatStream(
            { content: text.trim(), agent_type: agentMode },
            (event) => {
              setMessages((prev) => {
                const idx = prev.findIndex((m) => m.id === assistantId)
                if (idx === -1) return prev
                const updated = [...prev]
                const msg = { ...updated[idx] }

                if (event.event_type === 'start') {
                  msg.content = event.content as string
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
          )
        } catch (e) {
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
        } finally {
          setIsLoading(false)
        }
      } else {
        // 普通聊天模式
        try {
          const assistantMsg = await api.sendChatMessage({ content: text.trim() })
          setMessages((prev) => [
            ...prev,
            {
              ...assistantMsg,
              steps: undefined,
              isStreaming: false,
            },
          ])
        } catch (e) {
          toast.error(e instanceof Error ? e.message : '发送失败')
          setMessages((prev) => prev.filter((m) => m.id !== userMsg.id))
        } finally {
          setIsLoading(false)
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

  const currentMode = modeLabels[agentMode]
  const ModeIcon = currentMode.icon

  return (
    <AppShell>
      <div className="mx-auto flex h-[calc(100vh-4rem)] max-w-3xl flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
          <div className="flex items-center gap-3">
            <div className="relative" ref={modeMenuRef}>
              <button
                type="button"
                onClick={() => setShowModeMenu(!showModeMenu)}
                className="flex items-center gap-2 rounded-lg px-2 py-1 text-sm font-semibold text-white transition hover:bg-slate-800"
              >
                <ModeIcon size={18} className="text-amber-400" />
                {currentMode.label}
                <ChevronDown size={14} className="text-slate-400" />
              </button>
              {showModeMenu && (
                <div className="absolute left-0 top-full z-10 mt-1 w-56 rounded-lg border border-slate-700 bg-slate-900 py-1 shadow-lg">
                  {(Object.keys(modeLabels) as AgentMode[]).map((mode) => {
                    const { label, icon: Icon, desc } = modeLabels[mode]
                    return (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => {
                          setAgentMode(mode)
                          setShowModeMenu(false)
                        }}
                        className={`flex w-full items-start gap-2 px-3 py-2 text-left transition ${
                          agentMode === mode ? 'bg-slate-800' : 'hover:bg-slate-800'
                        }`}
                      >
                        <Icon size={16} className="mt-0.5 text-amber-400" />
                        <div>
                          <div className="text-sm font-medium text-white">{label}</div>
                          <div className="text-xs text-slate-400">{desc}</div>
                        </div>
                      </button>
                    )
                  })}
                </div>
              )}
            </div>
          </div>
          {messages.length > 0 && (
            <button
              type="button"
              onClick={handleClear}
              className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs text-slate-400 transition hover:bg-slate-800 hover:text-red-400"
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
                <ModeIcon size={24} className="text-amber-400" />
              </div>
              <div className="text-center">
                <h2 className="text-lg font-semibold text-white">{currentMode.label}</h2>
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
            <button
              type="button"
              onClick={() => handleSend(input)}
              disabled={isLoading || !input.trim()}
              className="mb-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-600 text-white transition hover:bg-amber-500 disabled:opacity-40"
            >
              <Send size={14} />
            </button>
          </div>
          <p className="mt-1.5 text-center text-[10px] text-slate-600">
            AI 回答仅供参考，不构成投资建议
            {agentMode === 'data' && ' · 数据助手会调用实时行情和品种数据库'}
            {agentMode === 'tech_analysis' && ' · 技术分析基于 10+ 经典指标进行综合评分'}
            {agentMode === 'risk_management' && ' · 风控方案基于账户 10 万模拟资金，支持自定义'}
            {agentMode === 'analysis_pipeline' && ' · 完整分析会串联数据、技术分析与风控三个 Agent'}
            {agentMode === 'factor_mining' && ' · 因子评估基于历史数据计算 IC、分层收益与最大回撤'}
            {agentMode === 'backtest' && ' · 策略回测会解析口头策略并计算收益、回撤、胜率和评分'}
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
          <FactorResultCard result={message.result} steps={message.steps} />
        )}

        {message.agentMode === 'tech_analysis' && !message.isStreaming && (
          <TechAnalysisReportCard result={message.result} />
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
