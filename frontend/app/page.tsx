'use client'

import { useCallback, useMemo } from 'react'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import LoginRequired from '@/components/auth/LoginRequired'
import { useAuth } from '@/components/auth/AuthProvider'
import EmptyState from '@/components/ui/EmptyState'
import ErrorState from '@/components/ui/ErrorState'
import RefreshStatus from '@/components/activity/RefreshStatus'
import MarketClosedBanner from '@/components/market/MarketClosedBanner'
import MarketSessionBadge from '@/components/market/MarketSessionBadge'
import PriceChange from '@/components/market/PriceChange'
import QuoteCard from '@/components/market/QuoteCard'
import { api, Product } from '@/lib/api'
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
        <div className="rounded-lg border border-slate-800 bg-surface p-8 text-center text-slate-400">
          正在确认登录状态...
        </div>
      ) : !isAuthenticated ? (
        <LoginRequired />
      ) : (
        <div className="space-y-6">
          <MarketClosedBanner />

          <section className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
            <div className="rounded-lg border border-slate-800 bg-surface p-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div>
                  <div className="flex items-center gap-3 text-sm text-slate-400">
                    <span className="flex items-center gap-2">
                      <BarChart3 size={16} />
                      30 秒自动刷新
                    </span>
                    <MarketSessionBadge />
                  </div>
                  <h1 className="mt-3 text-2xl font-bold text-white">行情工作台</h1>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-400">
                    聚合热门期货品种、实时涨跌和社区入口，快速进入单品种复盘与讨论。
                  </p>
                </div>
                <RefreshStatus heartbeat={heartbeat} onRefresh={refresh} className="sm:min-w-[330px]" />
              </div>

              <div className="mt-6 grid gap-3 sm:grid-cols-3">
                <Metric label="品种数" value={formatInteger(displayedProducts.length)} />
                <Metric label="上涨品种" value={`${upCount}/${displayedProducts.length || 0}`} tone="up" />
                <Metric label="总成交量" value={formatInteger(totalVolume)} />
              </div>
            </div>

            <div className="rounded-lg border border-slate-800 bg-black p-5">
              <div className="text-sm text-slate-500">领涨观察</div>
              {leader ? (
                <div className="mt-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="text-lg font-semibold">{leader.name}</div>
                      <div className="mt-1 font-mono text-xs text-slate-500">{leader.symbol}</div>
                    </div>
                    <PriceChange value={leader.change_percent} className="text-base" />
                  </div>
                  <div className="mt-5 font-mono text-3xl font-bold text-red-400">
                    {formatPrice(leader.current_price, leader.price_precision)}
                  </div>
                  <Link
                    href={`/products/${leader.symbol}`}
                    className="mt-5 inline-flex items-center gap-2 text-sm text-red-400 transition hover:text-red-300"
                  >
                    查看详情
                    <ArrowRight size={15} />
                  </Link>
                </div>
              ) : (
                <div className="mt-6 text-sm text-slate-500">等待行情数据同步</div>
              )}
            </div>
          </section>

          <section>
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">热门品种</h2>
                <p className="mt-1 text-sm text-slate-500">点击卡片进入品种详情页，查看品种技术分析、策略与评论</p>
              </div>
              <Link
                href="/products"
                className="inline-flex shrink-0 items-center gap-2 text-sm text-red-400 transition hover:text-red-300"
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
                action={
                  <button
                    type="button"
                    onClick={refresh}
                    className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700"
                  >
                    重新加载
                  </button>
                }
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

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'up' | 'down' }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-black/30 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-2 font-mono text-xl font-semibold ${tone ?? 'text-white'}`}>{value}</div>
    </div>
  )
}

function QuoteCardSkeleton({ count }: { count: number }) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="h-48 animate-pulse rounded-lg border border-slate-800 bg-surface p-4">
          <div className="h-4 w-1/3 rounded bg-slate-800" />
          <div className="mt-5 h-8 w-1/2 rounded bg-slate-800" />
          <div className="mt-6 grid grid-cols-2 gap-3">
            <div className="h-10 rounded bg-slate-800" />
            <div className="h-10 rounded bg-slate-800" />
          </div>
        </div>
      ))}
    </div>
  )
}
