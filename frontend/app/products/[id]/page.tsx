'use client'

import { FormEvent, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import dynamic from 'next/dynamic'
import AppShell from '@/components/layout/AppShell'

import LoginRequired from '@/components/auth/LoginRequired'
import { useAuth } from '@/components/auth/AuthProvider'
import EmptyState from '@/components/ui/EmptyState'
import ErrorState from '@/components/ui/ErrorState'
import PriceChange from '@/components/market/PriceChange'
import TechnicalAnalysisPanel from '@/components/market/TechnicalAnalysisPanel'
import { usePriceLevels } from '@/hooks/usePriceLevels'
import { api, Comment } from '@/lib/api'
import { captureMessage } from '@/lib/sentry-lite'
import { formatInteger, formatPrice, getChangeTone } from '@/lib/format'
import { toast } from 'sonner'
import {
  ArrowLeft,
  CheckCircle2,
  TrendingUp,
} from 'lucide-react'

import WatchlistButton from '@/components/product/WatchlistButton'
import { useProductKline } from '@/hooks/useProductKline'
import { useProductPolling } from '@/hooks/useProductPolling'
import TradingInfoPanel from '@/components/product/TradingInfoPanel'

const KlineSection = dynamic(() => import('@/components/product/KlineSection'), {
  ssr: false,
  loading: () => <div className="h-[520px] animate-pulse rounded-lg bg-slate-800" />,
})
import LevelEditor from '@/components/product/LevelEditor'
import CommentSection from '@/components/product/CommentSection'

export default function ProductDetailPage({ params }: { params: { id: string } }) {
  const symbol = params.id
  const { user, isAuthenticated, isLoading: authLoading } = useAuth()

  const {
    productDetail,
    product,
    realtime,
    varietyId,
    loading: isLoading,
    error,
    refresh: refreshProduct,
  } = useProductPolling(symbol, !authLoading && isAuthenticated)

  const [comments, setComments] = useState<Comment[]>([])
  const [newComment, setNewComment] = useState('')
  const [commentError, setCommentError] = useState<string | null>(null)
  const [isSubmittingComment, setIsSubmittingComment] = useState(false)
  const [newSupport, setNewSupport] = useState('')
  const [newResistance, setNewResistance] = useState('')
  const [isInWatchlist, setIsInWatchlist] = useState(false)
  const [watchlistId, setWatchlistId] = useState<number | null>(null)

  const {
    klineData,
    contracts,
    selectedContractId,
    selectedKlinePeriod,
    displayedKlinePeriod,
    selectedKlineSource,
    displayedKlineSource,
    klineNotice,
    isKlineLoading,
    isContractsLoading,
    setSelectedContractId,
    setSelectedKlinePeriod,
    setSelectedKlineSource,
  } = useProductKline(product?.symbol, isAuthenticated, varietyId)

  const {
    supportLevels,
    resistanceLevels,
    levelsLoaded,
    addSupport,
    addResistance,
    removeSupport,
    removeResistance,
  } = usePriceLevels({
    varietyId,
    userId: user?.id ?? null,
    symbol,
    source: selectedKlineSource,
    contractId: selectedContractId,
    pricePrecision: product?.price_precision,
  })

  useEffect(() => {
    if (productDetail?.comments) {
      setComments(productDetail.comments)
    }
  }, [productDetail])

  useEffect(() => {
    if (!varietyId) return
    let cancelled = false
    api.getWatchlists(varietyId)
      .then((list) => {
        if (cancelled) return
        if (list.length > 0) {
          setIsInWatchlist(true)
          setWatchlistId(list[0].id)
        } else {
          setIsInWatchlist(false)
          setWatchlistId(null)
        }
      })
      .catch((err) => {
        if (!cancelled) {
          captureMessage(
            `自选状态查询失败: varietyId=${varietyId}, ${err instanceof Error ? err.message : '未知错误'}`,
            'warning',
          )
          setIsInWatchlist(false)
          setWatchlistId(null)
        }
      })
    return () => { cancelled = true }
  }, [varietyId])

  const displayPrice = realtime?.current_price ?? product?.current_price
  const displayChange = realtime?.change_percent ?? product?.change_percent
  const marginCost = product?.margin != null && displayPrice != null
    ? displayPrice * product.margin / 100
    : null

  const sortedSupportLevels = useMemo(() => [...supportLevels].sort((a, b) => a - b), [supportLevels])
  const sortedResistanceLevels = useMemo(() => [...resistanceLevels].sort((a, b) => b - a), [resistanceLevels])

  const submitLevel = (value: string, type: 'support' | 'resistance') => {
    const price = Number.parseFloat(value)
    if (!Number.isFinite(price)) return
    if (type === 'support') {
      addSupport(price)
      setNewSupport('')
      captureMessage(`添加支撑位: ${symbol} @ ${price}`, 'info')
    } else {
      addResistance(price)
      setNewResistance('')
      captureMessage(`添加阻力位: ${symbol} @ ${price}`, 'info')
    }
  }

  const handleSubmitComment = async (event: FormEvent) => {
    event.preventDefault()
    if (!newComment.trim() || !user) return
    try {
      setIsSubmittingComment(true)
      setCommentError(null)
      const comment = await api.createComment(newComment.trim(), undefined, varietyId ?? undefined)
      setComments((current) => [comment, ...current])
      setNewComment('')
      toast.success('评论已发表')
      captureMessage(`用户发表评论: ${symbol}`, 'info')
    } catch (err) {
      setCommentError(err instanceof Error ? err.message : '评论发送失败')
    } finally {
      setIsSubmittingComment(false)
    }
  }

  return (
    <AppShell>
      {authLoading ? (
        <StatePanel>正在确认登录状态...</StatePanel>
      ) : !isAuthenticated ? (
        <LoginRequired />
      ) : isLoading ? (
        <StatePanel>正在加载品种详情...</StatePanel>
      ) : !product ? (
        error ? (
          <ErrorState message={error} onRetry={() => refreshProduct()} />
        ) : (
          <EmptyState title="品种不存在" description="没有找到对应的期货品种，请返回行情中心重新选择。" />
        )
      ) : (
        <div className="space-y-5">
          <div className="flex flex-col gap-4 rounded-lg border border-slate-800 bg-surface p-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <Link href="/products" className="inline-flex items-center gap-2 text-sm text-slate-400 transition hover:text-white">
                <ArrowLeft size={15} />
                返回行情中心
              </Link>
              <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-2">
                <h1 className="text-2xl font-bold text-white">{product.name}</h1>
                <span className="font-mono text-sm text-slate-500">{product.symbol}</span>
                {product.category && <span className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-400">{product.category}</span>}
                {varietyId && (
                  <WatchlistButton
                    varietyId={varietyId}
                    isInWatchlist={isInWatchlist}
                    watchlistId={watchlistId}
                    onToggle={(inList, id) => {
                      setIsInWatchlist(inList)
                      setWatchlistId(id)
                    }}
                  />
                )}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:min-w-[560px]">
              <QuoteMetric label="最新价" value={formatPrice(displayPrice, product?.price_precision)} tone={getChangeTone(displayChange)} />
              <QuoteMetric label="涨跌幅" value={<PriceChange value={displayChange} />} />
              <QuoteMetric label="最高" value={formatPrice(realtime?.high ?? product?.high, product?.price_precision)} />
              <QuoteMetric label="成交量" value={formatInteger(realtime?.volume ?? product?.volume)} />
            </div>
          </div>

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
            <section className="min-w-0 space-y-5">
              <div className="min-h-[420px] space-y-3">
                <KlineSection
                  data={klineData}
                  symbol={product.symbol}
                  pricePrecision={product.price_precision}
                  contracts={contracts}
                  selectedContractId={selectedContractId}
                  selectedSource={selectedKlineSource}
                  selectedPeriod={selectedKlinePeriod}
                  displayedSource={displayedKlineSource}
                  displayedPeriod={displayedKlinePeriod}
                  isLoading={isKlineLoading}
                  isContractsLoading={isContractsLoading}
                  notice={klineNotice}
                  viewportResetKey={`${product.symbol}:${displayedKlineSource}:${displayedKlinePeriod}:${selectedContractId ?? 'none'}`}
                  supportLevels={sortedSupportLevels}
                  resistanceLevels={sortedResistanceLevels}
                  onSelectContract={setSelectedContractId}
                  onSelectSource={setSelectedKlineSource}
                  onSelectPeriod={setSelectedKlinePeriod}
                  onAddSupport={addSupport}
                  onAddResistance={addResistance}
                  onRemoveSupport={removeSupport}
                  onRemoveResistance={removeResistance}
                />
              </div>

              <TechnicalAnalysisPanel
                data={klineData}
                currentPrice={displayPrice}
                supportLevels={sortedSupportLevels}
                resistanceLevels={sortedResistanceLevels}
              />

              <CommentSection
                comments={comments}
                commentError={commentError}
                isSubmitting={isSubmittingComment}
                newComment={newComment}
                onChangeComment={setNewComment}
                onSubmit={handleSubmitComment}
              />
            </section>

            <aside className="space-y-5">
              <TradingInfoPanel product={product} displayPrice={displayPrice} marginCost={marginCost} />

              <LevelEditor
                title="支撑位"
                icon={<CheckCircle2 size={16} className="text-green-400" />}
                tone="support"
                inputValue={newSupport}
                levels={sortedSupportLevels}
                isSaved={levelsLoaded}
                pricePrecision={product?.price_precision}
                onInputChange={setNewSupport}
                onAdd={() => submitLevel(newSupport, 'support')}
                onRemove={removeSupport}
              />

              <LevelEditor
                title="阻力位"
                icon={<TrendingUp size={16} className="text-red-400" />}
                tone="resistance"
                inputValue={newResistance}
                levels={sortedResistanceLevels}
                isSaved={levelsLoaded}
                pricePrecision={product?.price_precision}
                onInputChange={setNewResistance}
                onAdd={() => submitLevel(newResistance, 'resistance')}
                onRemove={removeResistance}
              />
            </aside>
          </div>
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

function QuoteMetric({
  label,
  value,
  tone,
}: {
  label: string
  value: React.ReactNode
  tone?: 'up' | 'down' | 'neutral'
}) {
  const toneClass = tone === 'up' ? 'text-red-400' : tone === 'down' ? 'text-green-400' : 'text-slate-200'
  return (
    <div className="rounded-lg border border-slate-800 bg-black/30 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-2 min-h-6 font-mono text-base font-semibold ${toneClass}`}>{value}</div>
    </div>
  )
}
