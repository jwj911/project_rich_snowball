import { FormEvent } from 'react'
import { RefreshCw, Send } from 'lucide-react'
import { Comment } from '@/lib/api'
import { formatDateTime } from '@/lib/format'

interface CommentPanelProps {
  comments: Comment[]
  commentError: string | null
  isSubmitting: boolean
  newComment: string
  onChangeComment: (value: string) => void
  onSubmit: (event: FormEvent) => void
}

export default function CommentPanel({
  comments,
  commentError,
  isSubmitting,
  newComment,
  onChangeComment,
  onSubmit,
}: CommentPanelProps) {
  return (
    <section className="rounded-lg border border-slate-800 bg-[#10161d] p-4">
      <h2 className="flex items-center gap-2 text-base font-semibold text-slate-200">
        <Send size={17} />
        评论区
      </h2>

      <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-2 sm:flex-row">
        <label htmlFor="product-comment-input" className="sr-only">发表评论</label>
        <input
          id="product-comment-input"
          type="text"
          value={newComment}
          onChange={(event) => onChangeComment(event.target.value)}
          placeholder="发表你的看法..."
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
                <span className="text-sm font-semibold text-red-300">{comment.username}</span>
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
