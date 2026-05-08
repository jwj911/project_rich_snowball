'use client'

import { useCallback, useMemo } from 'react'
import AppShell from '@/components/layout/AppShell'
import LoginRequired from '@/components/auth/LoginRequired'
import { useAuth } from '@/components/auth/AuthProvider'
import ErrorState from '@/components/ui/ErrorState'
import RefreshStatus from '@/components/activity/RefreshStatus'
import WorkspaceSummary from '@/components/workspace/WorkspaceSummary'
import MyAnnotationsPanel, { WorkspaceAnnotation } from '@/components/workspace/MyAnnotationsPanel'
import MyResearchTimeline from '@/components/workspace/MyResearchTimeline'
import WatchlistPanel from '@/components/workspace/WatchlistPanel'
import { api, Comment, Product } from '@/lib/api'
import { useMarketPolling } from '@/hooks/useMarketPolling'
import { Briefcase } from 'lucide-react'

interface WorkspaceData {
  comments: Comment[]
  products: Product[]
  annotations: WorkspaceAnnotation[]
}

interface SavedLevels {
  supportLevels?: unknown
  resistanceLevels?: unknown
  updatedAt?: unknown
}

export default function WorkspacePage() {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth()

  const fetchWorkspace = useCallback(async (): Promise<WorkspaceData> => {
    if (!user) {
      return { comments: [], products: [], annotations: [] }
    }

    const [comments, products] = await Promise.all([
      api.getUserComments(user.username),
      api.getProducts().catch(() => []),
    ])

    return {
      comments,
      products,
      annotations: readLocalAnnotations(user.id, products),
    }
  }, [user])

  const {
    data,
    loading,
    error,
    heartbeat,
    refresh,
  } = useMarketPolling<WorkspaceData>({
    enabled: !authLoading && isAuthenticated && Boolean(user),
    fetcher: fetchWorkspace,
    errorMessage: '工作区数据加载失败',
  })

  const comments = data?.comments ?? []
  const products = data?.products ?? []
  const annotations = data?.annotations ?? []
  const productMap = useMemo(() => new Map(products.map((product) => [product.id, product])), [products])
  const productCount = useMemo(() => new Set(comments.map((comment) => comment.product_id)).size, [comments])
  const annotationCount = annotations.reduce(
    (sum, annotation) => sum + annotation.supportLevels.length + annotation.resistanceLevels.length,
    0,
  )

  return (
    <AppShell>
      {authLoading ? (
        <StatePanel>正在确认登录状态...</StatePanel>
      ) : !isAuthenticated ? (
        <LoginRequired />
      ) : (
        <div className="space-y-5">
          <section className="rounded-lg border border-slate-800 bg-[#10161d] p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <div className="flex items-center gap-2 text-sm text-slate-400">
                  <Briefcase size={16} />
                  个人研究上下文
                </div>
                <h1 className="mt-3 text-2xl font-bold text-white">我的工作区</h1>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
                  聚合你的评论记录、本地价位标注和后续自选/预警入口。这里不会公开你的私密标注。
                </p>
              </div>
              <RefreshStatus heartbeat={heartbeat} onRefresh={refresh} className="lg:min-w-[360px]" />
            </div>
          </section>

          {error ? (
            <ErrorState message={error} onRetry={refresh} />
          ) : (
            <>
              <WorkspaceSummary
                commentCount={comments.length}
                productCount={productCount}
                annotationCount={annotationCount}
                watchlistCount={0}
              />

              {loading ? (
                <WorkspaceSkeleton />
              ) : (
                <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
                  <div className="space-y-5">
                    <MyResearchTimeline comments={comments} productMap={productMap} />
                    <MyAnnotationsPanel annotations={annotations} />
                  </div>
                  <WatchlistPanel products={products} />
                </div>
              )}
            </>
          )}
        </div>
      )}
    </AppShell>
  )
}

function readLocalAnnotations(userId: number, products: Product[]): WorkspaceAnnotation[] {
  if (typeof window === 'undefined') return []

  return products.flatMap((product) => {
    const raw = window.localStorage.getItem(`price-levels:v1:${userId}:${product.id}`)
    if (!raw) return []

    try {
      const parsed = JSON.parse(raw) as SavedLevels
      const supportLevels = normalizeLevels(parsed.supportLevels).sort((a, b) => a - b)
      const resistanceLevels = normalizeLevels(parsed.resistanceLevels).sort((a, b) => b - a)

      if (supportLevels.length === 0 && resistanceLevels.length === 0) return []

      return [{
        productId: product.id,
        productName: product.name,
        symbol: product.symbol,
        supportLevels,
        resistanceLevels,
        updatedAt: typeof parsed.updatedAt === 'string' ? parsed.updatedAt : undefined,
      }]
    } catch {
      return []
    }
  })
}

function normalizeLevels(value: unknown) {
  return Array.isArray(value)
    ? value.map((item) => Number(item)).filter(Number.isFinite)
    : []
}

function StatePanel({ children }: { children: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-[#10161d] p-8 text-center text-slate-400">
      {children}
    </div>
  )
}

function WorkspaceSkeleton() {
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="space-y-5">
        <div className="h-72 animate-pulse rounded-lg border border-slate-800 bg-[#10161d]" />
        <div className="h-72 animate-pulse rounded-lg border border-slate-800 bg-[#10161d]" />
      </div>
      <div className="h-80 animate-pulse rounded-lg border border-slate-800 bg-[#10161d]" />
    </div>
  )
}
