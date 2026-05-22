'use client'

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import dynamic from 'next/dynamic'
import AppShell from '@/components/layout/AppShell'

const KlineChart = dynamic(() => import('@/components/KlineChart'), {
  ssr: false,
  loading: () => <div className="h-[520px] animate-pulse rounded-lg bg-slate-800" />,
})
import LoginRequired from '@/components/auth/LoginRequired'
import { useAuth } from '@/components/auth/AuthProvider'
import EmptyState from '@/components/ui/EmptyState'
import ErrorState from '@/components/ui/ErrorState'
import PriceChange from '@/components/market/PriceChange'
import TechnicalAnalysisPanel from '@/components/market/TechnicalAnalysisPanel'
import { usePriceLevels } from '@/hooks/usePriceLevels'
import { api, Comment, KlineData, Product, RealtimeQuote } from '@/lib/api'
import { captureMessage } from '@/lib/sentry-lite'
import { formatInteger, formatNumber, getChangeTone } from '@/lib/format'
import { toast } from 'sonner'
import {
  ArrowLeft,
  CheckCircle2,
  TrendingUp,
} from 'lucide-react'

import WatchlistButton from '@/components/product/WatchlistButton'
import KlineToolbar, { KlinePeriod, KlineSource } from '@/components/product/KlineToolbar'
import TradingInfoPanel from '@/components/product/TradingInfoPanel'
import LevelEditor from '@/components/product/LevelEditor'
import CommentSection from '@/components/product/CommentSection'

const KLINE_PERIOD_LIMITS: Record<KlinePeriod, number> = {
  '1m': 120, '5m': 120, '15m': 120, '30m': 120,
  '1h': 100, '1d': 90, '1w': 90,
}

async function loadKlineBySource(
  symbol: string,
  source: KlineSource,
  period: KlinePeriod,
): Promise<{ rows: KlineData[]; period: KlinePeriod; notice: string | null }> {
  const limit = KLINE_PERIOD_LIMITS[period]
  try {
    let rows: KlineData[]
    switch (source) {
      case 'continuous':
        rows = await api.getContinuousKline(symbol, period, undefined, undefined, limit)
        break
      case 'main':
        rows = await api.getMainContractKline(symbol, period, undefined, undefined, limit)
        break
      default:
        rows = await api.getKline(symbol, period, limit)
        break
    }
    if (rows.length > 0) return { rows, period, notice: null }

    const sourceLabel = { continuous: '连续K线', main: '主力合约', single: '单合约' }[source]
    let notice = `${sourceLabel}（${period}）暂无 K 线数据`
    if (source === 'continuous') notice += '，可尝试切换至主力合约或单合约'
    else if (source === 'main') notice += '，可尝试切换至单合约'
    return { rows, period, notice }
  } catch (err) {
    return {
      rows: [],
      period,
      notice: err instanceof Error ? err.message : 'K 线数据加载失败',
    }
  }
}

export default function ProductDetailPage({ params }: { params: { id: string } }) {
  const productId = Number.parseInt(params.id, 10)
  const { user, isAuthenticated, isLoading: authLoading } = useAuth()
  const [product, setProduct] = useState<Product | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [newComment, setNewComment] = useState('')
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [commentError, setCommentError] = useState<string | null>(null)
  const [isSubmittingComment, setIsSubmittingComment] = useState(false)
  const [newSupport, setNewSupport] = useState('')
  const [newResistance, setNewResistance] = useState('')
  const [klineData, setKlineData] = useState<KlineData[]>([])
  const [selectedKlinePeriod, setSelectedKlinePeriod] = useState<KlinePeriod>('1d')
  const [displayedKlinePeriod, setDisplayedKlinePeriod] = useState<KlinePeriod>('1d')
  const [selectedKlineSource, setSelectedKlineSource] = useState<KlineSource>('continuous')
  const [displayedKlineSource, setDisplayedKlineSource] = useState<KlineSource>('continuous')
  const [klineNotice, setKlineNotice] = useState<string | null>(null)
  const [isKlineLoading, setIsKlineLoading] = useState(false)
  const [realtime, setRealtime] = useState<RealtimeQuote | null>(null)
  const [varietyId, setVarietyId] = useState<number | null>(null)
  const pollingInFlightRef = useRef(false)
  const [isInWatchlist, setIsInWatchlist] = useState(false)
  const [watchlistId, setWatchlistId] = useState<number | null>(null)

  const {
    supportLevels,
    resistanceLevels,
    levelsLoaded,
    addSupport,
    addResistance,
    removeSupport,
    removeResistance,
  } = usePriceLevels(varietyId, user?.id ?? null, productId)

  const loadData = useCallback(async (showLoading = true) => {
    if (!Number.isFinite(productId)) {
      setError('无效的品种 ID')
      setIsLoading(false)
      return
    }
    if (showLoading) setIsLoading(true)

    try {
      setError(null)
      const data = await api.getProduct(productId)
      setProduct(data.product)
      setComments(data.comments)

      if (data.product?.symbol) {
        const quote = await api.getRealtime(data.product.symbol).catch(() => null)
        setRealtime(quote)
        try {
          const variety = await api.getVariety(data.product.symbol)
          setVarietyId(variety.id)
        } catch {
          setVarietyId(null)
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '品种详情加载失败')
    } finally {
      setIsLoading(false)
    }
  }, [productId])

  useEffect(() => {
    if (authLoading) return
    if (!isAuthenticated) {
      setIsLoading(false)
      return
    }
    loadData()
    if (!Number.isFinite(productId)) return

    const interval = setInterval(async () => {
      if (pollingInFlightRef.current) return
      pollingInFlightRef.current = true
      try {
        const data = await api.getProduct(productId)
        setProduct(data.product)
        if (data.product?.symbol) {
          const quote = await api.getRealtime(data.product.symbol)
          setRealtime(quote)
        }
      } catch (err) {
        console.error('品种详情轮询失败:', err)
      } finally {
        pollingInFlightRef.current = false
      }
    }, 30000)

    return () => clearInterval(interval)
  }, [authLoading, isAuthenticated, loadData, productId])

  useEffect(() => {
    if (!product?.symbol || !isAuthenticated) return
    let cancelled = false
    setIsKlineLoading(true)
    setKlineNotice(null)

    loadKlineBySource(product.symbol, selectedKlineSource, selectedKlinePeriod)
      .then((kline) => {
        if (cancelled) return
        setKlineData(kline.rows)
        setDisplayedKlinePeriod(kline.period)
        setDisplayedKlineSource(selectedKlineSource)
        setKlineNotice(kline.notice)
      })
      .catch((err) => {
        if (cancelled) return
        setKlineData([])
        setKlineNotice(err instanceof Error ? err.message : 'K 线数据加载失败')
      })
      .finally(() => {
        if (!cancelled) setIsKlineLoading(false)
      })

    return () => { cancelled = true }
  }, [isAuthenticated, product?.symbol, selectedKlinePeriod, selectedKlineSource])

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
      .catch(() => {
        if (!cancelled) {
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
      captureMessage(`添加支撑位: 品种#${productId} @ ${price}`, 'info')
    } else {
      addResistance(price)
      setNewResistance('')
      captureMessage(`添加阻力位: 品种#${productId} @ ${price}`, 'info')
    }
  }

  const handleSubmitComment = async (event: FormEvent) => {
    event.preventDefault()
    if (!newComment.trim() || !user) return
    try {
      setIsSubmittingComment(true)
      setCommentError(null)
      const comment = await api.createComment(productId, newComment.trim())
      setComments((current) => [comment, ...current])
      setNewComment('')
      toast.success('评论已发表')
      captureMessage(`用户发表评论: 品种#${productId}`, 'info')
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
          <ErrorState message={error} onRetry={() => loadData()} />
        ) : (
          <EmptyState title="品种不存在" description="没有找到对应的期货品种，请返回行情中心重新选择。" />
        )
      ) : (
        <div className="space-y-5">
          <div className="flex flex-col gap-4 rounded-lg border border-slate-800 bg-[#10161d] p-4 lg:flex-row lg:items-center lg:justify-between">
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
              <QuoteMetric label="最新价" value={formatNumber(displayPrice)} tone={getChangeTone(displayChange)} />
              <QuoteMetric label="涨跌幅" value={<PriceChange value={displayChange} />} />
              <QuoteMetric label="最高" value={formatNumber(realtime?.high ?? product.high)} />
              <QuoteMetric label="成交量" value={formatInteger(realtime?.volume ?? product.volume)} />
            </div>
          </div>

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_320px]">
            <section className="min-w-0 space-y-5">
              <div className="min-h-[420px] space-y-3">
                <KlineToolbar
                  selectedSource={selectedKlineSource}
                  selectedPeriod={selectedKlinePeriod}
                  displayedSource={displayedKlineSource}
                  displayedPeriod={displayedKlinePeriod}
                  isLoading={isKlineLoading}
                  onSourceChange={setSelectedKlineSource}
                  onPeriodChange={setSelectedKlinePeriod}
                />

                {klineNotice && (
                  <div className="mb-3 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
                    {klineNotice}
                  </div>
                )}

                <KlineChart
                  data={klineData}
                  symbol={product.symbol}
                  supportLevels={sortedSupportLevels}
                  resistanceLevels={sortedResistanceLevels}
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
    <div className="rounded-lg border border-slate-800 bg-[#10161d] p-8 text-center text-slate-400">
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
  tone?: 'up' | 'down'
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-black/30 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-2 min-h-6 font-mono text-base font-semibold ${tone ?? 'text-slate-200'}`}>{value}</div>
    </div>
  )
}
