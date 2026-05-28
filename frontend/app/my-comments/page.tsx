'use client'

import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import LoginRequired from '@/components/auth/LoginRequired'
import { useAuth } from '@/components/auth/AuthProvider'
import EmptyState from '@/components/ui/EmptyState'
import ErrorState from '@/components/ui/ErrorState'
import { useUserComments } from '@/lib/swr-hooks'
import { api, Product } from '@/lib/api'
import { formatDateTime } from '@/lib/format'
import { ArrowRight, MessageSquare, RefreshCw } from 'lucide-react'
import useSWR from 'swr'

export default function MyCommentsPage() {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth()
  const username = user?.username ?? null

  const {
    data: comments,
    error: commentError,
    isLoading: commentsLoading,
    mutate: mutateComments,
  } = useUserComments(username)

  const {
    data: products,
    isLoading: productsLoading,
  } = useSWR(
    isAuthenticated ? 'my-comments-products' : null,
    () => api.getProducts().catch(() => [] as Product[]),
    { revalidateOnFocus: false },
  )

  const loading = authLoading || commentsLoading || productsLoading
  const productMap = new Map((products ?? []).map((p) => [p.symbol, p]))
  const productCount = new Set((comments ?? []).map((c) => c.product_symbol)).size

  return (
    <AppShell>
      {authLoading ? (
        <StatePanel>正在确认登录状态...</StatePanel>
      ) : !isAuthenticated ? (
        <LoginRequired />
      ) : (
        <div className="space-y-5">
          <section className="rounded-lg border border-slate-800 bg-surface p-5">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <h1 className="text-2xl font-bold">我的评论</h1>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  {user ? `${user.username} 的社区发言记录` : '社区发言记录'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => mutateComments()}
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 transition hover:border-red-800 hover:text-white"
              >
                <RefreshCw size={15} />
                刷新
              </button>
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-3">
              <Metric label="评论数" value={String((comments ?? []).length)} />
              <Metric
                label="最近发言"
                value={comments?.[0]?.created_at ? formatDateTime(comments[0].created_at) : '--'}
              />
              <Metric label="涉及品种" value={String(productCount)} />
            </div>
          </section>

          {loading ? (
            <CommentSkeleton />
          ) : commentError ? (
            <ErrorState message={commentError instanceof Error ? commentError.message : '评论记录加载失败'} onRetry={() => mutateComments()} />
          ) : (comments ?? []).length === 0 ? (
            <EmptyState
              icon={MessageSquare}
              title="暂无评论"
              description="进入品种详情页，记录你的行情判断和复盘想法。"
              action={
                <Link
                  href="/products"
                  className="inline-flex items-center gap-2 rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700"
                >
                  浏览品种
                  <ArrowRight size={15} />
                </Link>
              }
            />
          ) : (
            <section className="space-y-3">
              {(comments ?? []).map((comment) => (
                <CommentCard key={comment.id} comment={comment} product={productMap.get(comment.product_symbol ?? '')} />
              ))}
            </section>
          )}
        </div>
      )}
    </AppShell>
  )
}

function StatePanel({ children }: { children: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-surface p-8 text-center text-slate-400">
      {children}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-black/30 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="mt-2 truncate font-mono text-base font-semibold text-slate-200">{value}</div>
    </div>
  )
}

function CommentCard({ comment, product }: { comment: { id: number; product_id: number; product_symbol: string | null; username: string; content: string; created_at: string }; product?: Product }) {
  const productLabel = product ? `${product.name} ${product.symbol}` : (comment.product_symbol ?? `品种 #${comment.product_id}`)

  return (
    <Link
      href={`/products/${comment.product_symbol ?? comment.product_id}`}
      className="group block rounded-lg border border-slate-800 bg-surface p-4 transition hover:border-red-800/80 hover:bg-[#121b24]"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="rounded border border-slate-700 px-2 py-0.5 font-mono text-xs text-slate-400">
            {productLabel}
          </span>
          <span className="text-sm text-slate-500">{comment.username}</span>
        </div>
        <span className="font-mono text-xs text-slate-600">{formatDateTime(comment.created_at)}</span>
      </div>
      <p className="mt-3 text-sm leading-6 text-slate-300">{comment.content}</p>
      <div className="mt-4 inline-flex items-center gap-1 rounded-lg border border-red-900/50 px-3 py-1.5 text-sm text-red-300 transition group-hover:border-red-700 group-hover:text-red-200">
        查看品种详情
        <ArrowRight size={14} />
      </div>
    </Link>
  )
}

function CommentSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="h-28 animate-pulse rounded-lg border border-slate-800 bg-surface p-4">
          <div className="h-4 w-32 rounded bg-slate-800" />
          <div className="mt-4 h-3 w-3/4 rounded bg-slate-800" />
          <div className="mt-2 h-3 w-1/2 rounded bg-slate-800" />
        </div>
      ))}
    </div>
  )
}
