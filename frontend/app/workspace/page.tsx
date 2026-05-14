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
import { api, Comment, Product, PriceLevel, Watchlist, Variety } from '@/lib/api'
import { useMarketPolling } from '@/hooks/useMarketPolling'
import { useWatchlistRealtime } from '@/hooks/useWatchlistRealtime'
import { Briefcase } from 'lucide-react'

interface WorkspaceData {
  comments: Comment[]
  products: Product[]
  annotations: WorkspaceAnnotation[]
  watchlists: Watchlist[]
}

const EMPTY_COMMENTS: Comment[] = []
const EMPTY_PRODUCTS: Product[] = []
const EMPTY_ANNOTATIONS: WorkspaceAnnotation[] = []
const EMPTY_WATCHLISTS: Watchlist[] = []

export default function WorkspacePage() {
  const { user, isAuthenticated, isLoading: authLoading } = useAuth()

  const fetchWorkspace = useCallback(async (): Promise<WorkspaceData> => {
    if (!user) {
      return { comments: [], products: [], annotations: [], watchlists: [] }
    }

    const [workspace, products, varieties] = await Promise.all([
      api.getWorkspace().catch(() => null),
      api.getProducts().catch(() => []),
      api.getVarieties().catch(() => []),
    ])

    const priceLevels = workspace?.price_levels ?? []
    const watchlists = workspace?.watchlists ?? []
    const comments = workspace?.recent_comments ?? []

    const annotations = buildAnnotations(priceLevels, varieties, products)

    return {
      comments,
      products,
      annotations,
      watchlists,
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

  const comments = data?.comments ?? EMPTY_COMMENTS
  const products = data?.products ?? EMPTY_PRODUCTS
  const annotations = data?.annotations ?? EMPTY_ANNOTATIONS
  const watchlists = data?.watchlists ?? EMPTY_WATCHLISTS

  const watchlistSymbols = useMemo(() => watchlists.map((w) => w.variety_symbol), [watchlists])
  const { quotes: watchlistRealtime } = useWatchlistRealtime(watchlistSymbols)

  const productMap = useMemo(() => new Map(products.map((product) => [product.id, product])), [products])
  const productCount = useMemo(() => new Set(comments.map((comment) => comment.product_id)).size, [comments])
  const annotationCount = annotations.reduce(
    (sum, annotation) => sum + annotation.supportLevels.length + annotation.resistanceLevels.length,
    0,
  )

  const handleDeleteWatchlist = useCallback(async (id: number) => {
    try {
      await api.deleteWatchlist(id)
      refresh()
    } catch {
      // 错误由 useMarketPolling 处理，这里静默失败
    }
  }, [refresh])

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
                  聚合你的评论记录、价位标注和自选观察。数据已同步到云端，换设备后仍然保留。
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
                watchlistCount={watchlists.length}
              />

              {loading ? (
                <WorkspaceSkeleton />
              ) : (
                <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
                  <div className="space-y-5">
                    <MyResearchTimeline comments={comments} productMap={productMap} />
                    <MyAnnotationsPanel annotations={annotations} />
                  </div>
                  <WatchlistPanel
                    watchlists={watchlists}
                    products={products}
                    realtimeQuotes={watchlistRealtime}
                    onDelete={handleDeleteWatchlist}
                  />
                </div>
              )}
            </>
          )}
        </div>
      )}
    </AppShell>
  )
}

function buildAnnotations(
  priceLevels: PriceLevel[],
  varieties: Variety[],
  products: Product[],
): WorkspaceAnnotation[] {
  const varietyMap = new Map(varieties.map((v) => [v.id, v]))
  const symbolToProduct = new Map(products.map((p) => [p.symbol, p]))

  const byVariety = new Map<number, PriceLevel[]>()
  for (const pl of priceLevels) {
    const list = byVariety.get(pl.variety_id) ?? []
    list.push(pl)
    byVariety.set(pl.variety_id, list)
  }

  const annotations: WorkspaceAnnotation[] = []
  byVariety.forEach((levels, varietyId) => {
    const variety = varietyMap.get(varietyId)
    if (!variety) return

    const product = symbolToProduct.get(variety.symbol)
    if (!product) return

    const supportLevels = levels
      .filter((l: PriceLevel) => l.type === 'support')
      .map((l: PriceLevel) => Number(l.price))
      .filter(Number.isFinite)
      .sort((a: number, b: number) => a - b)

    const resistanceLevels = levels
      .filter((l: PriceLevel) => l.type === 'resistance')
      .map((l: PriceLevel) => Number(l.price))
      .filter(Number.isFinite)
      .sort((a: number, b: number) => b - a)

    if (supportLevels.length === 0 && resistanceLevels.length === 0) return

    annotations.push({
      productId: product.id,
      productName: product.name,
      symbol: product.symbol,
      supportLevels,
      resistanceLevels,
    })
  })

  return annotations
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
