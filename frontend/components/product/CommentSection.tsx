'use client'

import { FormEvent, useState } from 'react'
import { Send, RefreshCw, TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { Comment } from '@/lib/api'
import { formatDateTime } from '@/lib/format'

type Sentiment = 'bullish' | 'bearish' | 'neutral'

const sentimentConfig: Record<Sentiment, { label: string; icon: typeof TrendingUp; color: string; activeClass: string }> = {
  bullish: {
    label: '看多',
    icon: TrendingUp,
    color: 'text-red-400',
    activeClass: 'bg-red-500/20 border-red-500/50 text-red-300',
  },
  bearish: {
    label: '看空',
    icon: TrendingDown,
    color: 'text-green-400',
    activeClass: 'bg-green-500/20 border-green-500/50 text-green-300',
  },
  neutral: {
    label: '观望',
    icon: Minus,
    color: 'text-slate-400',
    activeClass: 'bg-slate-500/20 border-slate-500/50 text-slate-300',
  },
}

interface CommentSectionProps {
  comments: Comment[]
  commentError: string | null
  isSubmitting: boolean
  newComment: string
  onChangeComment: (value: string) => void
  onSubmit: (event: FormEvent, sentiment: Sentiment | null) => void
}

export default function CommentSection({
  comments,
  commentError,
  isSubmitting,
  newComment,
  onChangeComment,
  onSubmit,
}: CommentSectionProps) {
  const [sentiment, setSentiment] = useState<Sentiment | null>(null)

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit(event, sentiment)
    setSentiment(null)
  }

  return (
    <section className="rounded-lg border border-slate-800 bg-surface p-4">
      <h2 className="flex items-center gap-2 text-base font-semibold text-slate-200">
        <Send size={17} />
        评论与观点
      </h2>

      {/* Sentiment selector */}
      <div className="mt-3 flex items-center gap-2">
        <span className="text-xs text-slate-500">表态：</span>
        {(Object.keys(sentimentConfig) as Sentiment[]).map((key) => {
          const cfg = sentimentConfig[key]
          const Icon = cfg.icon
          const isActive = sentiment === key
          return (
            <button
              key={key}
              type="button"
              onClick={() => setSentiment(isActive ? null : key)}
              className={`inline-flex items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition ${
                isActive
                  ? cfg.activeClass
                  : 'border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
              }`}
            >
              <Icon size={12} className={isActive ? cfg.color : ''} />
              {cfg.label}
            </button>
          )
        })}
        {sentiment && (
          <button
            type="button"
            onClick={() => setSentiment(null)}
            className="ml-auto text-xs text-slate-500 transition hover:text-slate-300"
          >
            清除
          </button>
        )}
      </div>

      <form onSubmit={handleSubmit} className="mt-2 flex flex-col gap-2 sm:flex-row">
        <label htmlFor="product-comment-input" className="sr-only">发表评论</label>
        <input
          id="product-comment-input"
          type="text"
          value={newComment}
          onChange={(event) => onChangeComment(event.target.value)}
          placeholder={sentiment ? `发表${sentimentConfig[sentiment].label}观点...` : '发表你的看法...'}
          className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white outline-none placeholder:text-slate-600 focus:border-red-800"
        />
        <button
          type="submit"
          disabled={isSubmitting || !newComment.trim()}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-red-700 disabled:cursor-not-allowed disabled:bg-slate-700 disabled:text-slate-400"
        >
          {isSubmitting ? (
            <>
              <RefreshCw size={15} className="animate-spin" />
              发送中
            </>
          ) : (
            '发送'
          )}
        </button>
      </form>

      {commentError && (
        <div className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-100">
          {commentError}
        </div>
      )}

      <div className="mt-4 max-h-64 space-y-2 overflow-y-auto pr-1">
        {comments.length === 0 ? (
          <div className="rounded-lg border border-slate-800 bg-black/20 p-4 text-sm text-slate-500">暂无评论</div>
        ) : (
          comments.map((comment) => (
            <article key={comment.id} className="rounded-lg border border-slate-800 bg-black/20 px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-red-300">{comment.username}</span>
                  {comment.sentiment && sentimentConfig[comment.sentiment as Sentiment] && (
                    <SentimentBadge sentiment={comment.sentiment as Sentiment} />
                  )}
                </div>
                <span className="font-mono text-xs text-slate-600">{formatDateTime(comment.created_at)}</span>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-300">{comment.content}</p>
            </article>
          ))
        )}
      </div>
    </section>
  )
}

function SentimentBadge({ sentiment }: { sentiment: Sentiment }) {
  const cfg = sentimentConfig[sentiment]
  const Icon = cfg.icon
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium ${cfg.activeClass}`}>
      <Icon size={10} />
      {cfg.label}
    </span>
  )
}
