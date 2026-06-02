'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import AppShell from '@/components/layout/AppShell'
import EmptyState from '@/components/ui/EmptyState'
import { api, type ChatMessage } from '@/lib/api'
import { formatPrice } from '@/lib/format'
import {
  Send,
  Trash2,
  Bot,
  User,
  Sparkles,
  Loader2,
  Zap,
} from 'lucide-react'
import { toast } from 'sonner'

const quickPrompts = [
  '分析一下螺纹钢最近的走势',
  '黄金目前适合做多还是做空？',
  '帮我总结今天的热门品种',
  '原油期货有什么新闻？',
]

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isLoadingHistory, setIsLoadingHistory] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    api
      .getChatHistory({ limit: 100 })
      .then((history) => {
        if (!cancelled) setMessages(history)
      })
      .catch(() => {
        if (!cancelled) toast.error('加载历史记录失败')
      })
      .finally(() => {
        if (!cancelled) setIsLoadingHistory(false)
      })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = useCallback(
    async (text: string) => {
      if (!text.trim() || isLoading) return
      const userMsg: ChatMessage = {
        id: Date.now(),
        role: 'user',
        content: text.trim(),
        created_at: new Date().toISOString(),
      }
      setMessages((prev) => [...prev, userMsg])
      setInput('')
      setIsLoading(true)

      try {
        const assistantMsg = await api.sendChatMessage({ content: text.trim() })
        setMessages((prev) => [...prev, assistantMsg])
      } catch (e) {
        toast.error(e instanceof Error ? e.message : '发送失败')
        setMessages((prev) => prev.filter((m) => m.id !== userMsg.id))
      } finally {
        setIsLoading(false)
      }
    },
    [isLoading],
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

  return (
    <AppShell>
      <div className="mx-auto flex h-[calc(100vh-4rem)] max-w-3xl flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-amber-400" />
            <h1 className="text-base font-semibold text-white">AI 助手</h1>
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
                <Bot size={24} className="text-amber-400" />
              </div>
              <div className="text-center">
                <h2 className="text-lg font-semibold text-white">期货 AI 助手</h2>
                <p className="mt-1 text-sm text-slate-400">问我关于期货行情、交易观点或投资策略的问题</p>
              </div>
              <div className="flex flex-wrap justify-center gap-2">
                {quickPrompts.map((prompt) => (
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
              {isLoading && (
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-500/10">
                    <Zap size={14} className="text-amber-400" />
                  </div>
                  <div className="rounded-xl border border-slate-800 bg-surface px-4 py-3">
                    <Loader2 size={16} className="animate-spin text-slate-400" />
                  </div>
                </div>
              )}
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
              placeholder="输入问题，Shift+Enter 换行..."
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
          </p>
        </div>
      </div>
    </AppShell>
  )
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'

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
        <div className="whitespace-pre-wrap">{message.content}</div>
      </div>
    </div>
  )
}
