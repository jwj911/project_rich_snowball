import Link from 'next/link'
import EmptyState from '@/components/ui/EmptyState'
import { Comment, Product } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { ArrowRight, MessageSquare } from 'lucide-react'

export default function MyResearchTimeline({
  comments,
  productMap,
}: {
  comments: Comment[]
  productMap: Map<string, Product>
}) {
  return (
    <section className="rounded-lg border border-slate-800 bg-surface p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">研究时间线</h2>
          <p className="mt-1 text-xs text-slate-500">按时间回看你的评论和复盘线索。</p>
        </div>
        <Link href="/my-comments" className="inline-flex items-center gap-1 text-xs text-red-300 hover:text-red-200">
          全部
          <ArrowRight size={13} />
        </Link>
      </div>

      {comments.length === 0 ? (
        <EmptyState
          icon={MessageSquare}
          title="暂无评论记录"
          description="在品种详情页发表观点后，这里会形成你的研究时间线。"
          className="mt-4 bg-black/20"
        />
      ) : (
        <div className="mt-4 space-y-3">
          {comments.slice(0, 6).map((comment) => {
            const product = productMap.get(comment.product_symbol ?? '')
            const productLabel = product ? `${product.name} ${product.symbol}` : (comment.product_symbol ?? `品种 #${comment.product_id}`)

            return (
              <Link
                key={comment.id}
                href={`/products/${comment.product_symbol ?? comment.product_id}`}
                className="group block rounded-lg border border-slate-800 bg-black/20 p-3 transition hover:border-red-800/80 hover:bg-[#121b24]"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="rounded border border-slate-700 px-2 py-0.5 font-mono text-xs text-slate-400">
                    {productLabel}
                  </span>
                  <span className="font-mono text-xs text-slate-600">{formatDateTime(comment.created_at)}</span>
                </div>
                <p className="mt-3 line-clamp-2 text-sm leading-6 text-slate-300">{comment.content}</p>
                <div className="mt-3 text-xs text-red-300 opacity-0 transition group-hover:opacity-100">查看详情</div>
              </Link>
            )
          })}
        </div>
      )}
    </section>
  )
}
