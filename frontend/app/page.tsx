'use client'

import { useMemo } from 'react'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import LoginRequired from '@/components/auth/LoginRequired'
import { useAuth } from '@/components/auth/AuthProvider'
import Card from '@/components/ui/Card'
import EmptyState from '@/components/ui/EmptyState'
import ErrorState from '@/components/ui/ErrorState'
import MetricCard from '@/components/ui/MetricCard'
import RefreshStatus from '@/components/activity/RefreshStatus'
import MarketClosedBanner from '@/components/market/MarketClosedBanner'
import MarketSessionBadge from '@/components/market/MarketSessionBadge'
import PriceChange from '@/components/market/PriceChange'
import QuoteCard from '@/components/market/QuoteCard'
import Skeleton from '@/components/ui/Skeleton'
import { Product } from '@/lib/api'
import { formatInteger, formatPrice } from '@/lib/format'
import { useProductListRealtime } from '@/hooks/useProductListRealtime'
import { ArrowRight, BarChart3, Search } from 'lucide-react'

const EMPTY_PRODUCTS: Product[] = []

export default function HomePage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const {
    products,
    loading,
    error,
    heartbeat,
    refresh,
  } = useProductListRealtime(!authLoading && isAuthenticated)
  const displayedProducts = products ?? EMPTY_PRODUCTS

  const hotProducts = useMemo(() => displayedProducts.slice(0, 6), [displayedProducts])
  const leader = hotProducts[0]
  const totalVolume = useMemo(
    () => displayedProducts.reduce((sum, product) => sum + (product.volume ?? 0), 0),
    [displayedProducts],
  )
  const upCount = displayedProducts.filter((product) => (product.change_percent ?? 0) >= 0).length

  return (
    <AppShell>
      {authLoading ? (
        <Card className="p-8 text-center text-gray-800">正在确认登录状态…</Card>
      ) : !isAuthenticated ? (
        <LoginRequired />
      ) : (
        <div className="space-y-8">
          <MarketClosedBanner />

          <section className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <Card>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="flex items-center gap-3 text-label-14 text-gray-800">
                    <span className="flex items-center gap-2">
                      <BarChart3 size={16} />
                      行情数据
                    </span>
                    <MarketSessionBadge />
                  </div>
                  <h1 className="mt-3 text-heading-24 text-foreground">行情工作台</h1>
                  <p className="mt-2 max-w-2xl text-copy-14 text-gray-800">
                    聚合热门期货品种、实时涨跌和社区入口，快速进入单品种复盘与讨论。
                  </p>
                </div>
                <RefreshStatus heartbeat={heartbeat} onRefresh={refresh} className="sm:min-w-[330px]" />
              </div>

              <div className="mt-6 grid gap-3 sm:grid-cols-3">
                <MetricCard label="品种数" value={formatInteger(displayedProducts.length)} />
                <MetricCard label="上涨品种" value={`${upCount}/${displayedProducts.length || 0}`} tone="up" />
                <MetricCard label="总成交量" value={formatInteger(totalVolume)} />
              </div>
            </Card>

            <Card className="bg-gray-100">
              <div className="text-label-14 text-gray-700">领涨观察</div>
              {leader ? (
                <div className="mt-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-heading-20 text-foreground">{leader.name}</div>
                      <div className="mt-1 font-mono text-label-12 text-gray-700">{leader.symbol}</div>
                    </div>
                    <PriceChange value={leader.change_percent} className="text-base" />
                  </div>
                  <div className="mt-5 font-mono text-copy-24 font-semibold text-up">
                    {formatPrice(leader.current_price, leader.price_precision)}
                  </div>
                  <Link
                    href={`/products/${leader.symbol}`}
                    className="mt-5 inline-flex items-center gap-2 text-label-14 text-up transition hover:text-red-900"
                  >
                    查看详情
                    <ArrowRight size={15} />
                  </Link>
                </div>
              ) : (
                <div className="mt-6 text-label-14 text-gray-700">等待行情数据同步</div>
              )}
            </Card>
          </section>

          <section>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-heading-20 text-foreground">热门品种</h2>
                <p className="mt-1 text-copy-14 text-gray-700">点击卡片进入品种详情页，查看品种技术分析、策略与评论</p>
              </div>
              <Link
                href="/products"
                className="inline-flex shrink-0 items-center gap-2 text-label-14 text-up transition hover:text-red-900"
              >
                全部品种
                <ArrowRight size={15} />
              </Link>
            </div>

            {loading ? (
              <QuoteCardSkeleton count={6} />
            ) : error ? (
              <ErrorState message={error} onRetry={refresh} />
            ) : hotProducts.length === 0 ? (
              <EmptyState
                icon={Search}
                title="暂无行情品种"
                description="当前没有可展示的期货品种，请稍后重试或检查后端数据同步状态。"
              />
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                {hotProducts.map((product) => (
                  <QuoteCard key={product.id} product={product} />
                ))}
              </div>
            )}
          </section>
        </div>
      )}
    </AppShell>
  )
}

function QuoteCardSkeleton({ count }: { count: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: count }).map((_, index) => (
        <Card key={index} padding="md" className="h-48">
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="mt-5 h-8 w-1/2" />
          <div className="mt-6 grid grid-cols-2 gap-3">
            <Skeleton className="h-10" />
            <Skeleton className="h-10" />
          </div>
        </Card>
      ))}
    </div>
  )
}
