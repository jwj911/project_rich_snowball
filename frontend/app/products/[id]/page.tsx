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
import { api, Comment, ContractRollover } from '@/lib/api'
import { captureMessage } from '@/lib/sentry-lite'
import { formatDateOnly, formatInteger, formatPrice, getChangeTone } from '@/lib/format'
import { toast } from 'sonner'
import useSWR from 'swr'
import { ArrowLeft, CheckCircle2, TrendingUp, Plus, Trash2, Bell } from 'lucide-react'
import type { PriceAlert } from '@/lib/api'

import WatchlistButton from '@/components/product/WatchlistButton'
import { useProductKline } from '@/hooks/useProductKline'
import { useProductPolling } from '@/hooks/useProductPolling'
import TradingInfoPanel from '@/components/product/TradingInfoPanel'
import ContractRolloverPanel from '@/components/product/ContractRolloverPanel'

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
  const [watchlistLoadedFor, setWatchlistLoadedFor] = useState<number | null>(null)
  const [rollovers, setRollovers] = useState<ContractRollover[]>([])
  const [rolloversLoading, setRolloversLoading] = useState(false)
  const [showAlertForm, setShowAlertForm] = useState(false)
  const [alertType, setAlertType] = useState<'above' | 'below'>('above')
  const [alertPrice, setAlertPrice] = useState('')

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
    if (!varietyId) {
      setWatchlistLoadedFor(null)
      return
    }
    let cancelled = false
    setWatchlistLoadedFor(null)
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
      .finally(() => {
        if (!cancelled) setWatchlistLoadedFor(varietyId)
      })
    return () => { cancelled = true }
  }, [varietyId])

  useEffect(() => {
    if (!varietyId || !isAuthenticated) {
      setRollovers([])
      return
    }
    let cancelled = false
    setRolloversLoading(true)
    api.getContractRollovers(varietyId, { limit: 20 })
      .then((rows) => {
        if (!cancelled) setRollovers(rows)
      })
      .catch((err) => {
        if (!cancelled) {
          captureMessage(
            `合约切换历史加载失败: varietyId=${varietyId}, ${err instanceof Error ? err.message : '未知错误'}`,
            'warning',
          )
        }
      })
      .finally(() => {
        if (!cancelled) setRolloversLoading(false)
      })
    return () => { cancelled = true }
  }, [varietyId, isAuthenticated])

  const displayPrice = realtime?.current_price ?? product?.current_price
  const displayChange = realtime?.change_percent ?? product?.change_percent
  const displaySettle = product?.settle
  const displayClosePrice = product?.close_price
  const displayOiChg = product?.oi_chg
  const displayTradeDate = product?.trade_date
    ? formatDateOnly(product.trade_date)
    : null
  const marginCost = product?.margin != null && displaySettle != null
    ? displaySettle * product.margin / 100
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

  const handleSubmitComment = async (_event: FormEvent, sentiment: 'bullish' | 'bearish' | 'neutral' | null) => {
    if (!newComment.trim() || !user) return
    try {
      setIsSubmittingComment(true)
      setCommentError(null)
      const comment = await api.createComment(newComment.trim(), undefined, varietyId ?? undefined, sentiment ?? undefined)
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

  const {
    data: priceAlerts,
    mutate: mutateAlerts,
  } = useSWR(
    varietyId ? ['price-alerts', varietyId] : null,
    () => api.getPriceAlerts({ variety_id: varietyId! }),
    { revalidateOnFocus: false },
  )

  const handleCreateAlert = async () => {
    if (!varietyId || !alertPrice.trim()) return
    const price = Number.parseFloat(alertPrice)
    if (!Number.isFinite(price) || price <= 0) {
      toast.error('请输入有效的目标价格')
      return
    }
    try {
      await api.createPriceAlert({
        variety_id: varietyId,
        alert_type: alertType,
        target_price: alertPrice,
      })
      toast.success('预警已设置')
      setAlertPrice('')
      setShowAlertForm(false)
      mutateAlerts()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '设置失败')
    }
  }

  const handleDeleteAlert = async (id: number) => {
    if (!confirm('确定删除这条预警？')) return
    try {
      await api.deletePriceAlert(id)
      toast.success('预警已删除')
      mutateAlerts()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '删除失败')
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
          <div className="flex flex-col gap-5 rounded border border-gray-alpha-400 bg-background p-5 lg:flex-row lg:items-start lg:justify-between">
            {/* 左侧：品种信息 */}
            <div className="min-w-0">
              <Link href="/products" className="inline-flex items-center gap-2 text-label-14 text-gray-700 transition hover:text-foreground">
                <ArrowLeft size={15} />
                返回行情中心
              </Link>
              <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2">
                <h1 className="text-heading-28 text-foreground">{product.name}</h1>
                <span className="font-mono text-label-16 text-gray-700">{product.symbol}</span>
                {product.category && (
                  <span className="rounded border border-gray-alpha-400 bg-gray-100 px-2.5 py-1 text-label-13 text-gray-800">{product.category}</span>
                )}
                {varietyId && watchlistLoadedFor === varietyId && (
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

            {/* 右侧：行情数据 */}
            <div className="flex flex-col gap-4 lg:items-end">
              {/* 第一行：收盘价 + 涨跌幅 + 结算价 */}
              <div className="flex items-baseline gap-5">
                <div>
                  <div className="text-label-12 text-gray-700">收盘价</div>
                  <div className={`mt-1 font-mono text-heading-32 font-bold ${getChangeTone(displayChange) === 'up' ? 'text-up' : getChangeTone(displayChange) === 'down' ? 'text-down' : 'text-foreground'}`}>
                    {formatPrice(displayClosePrice, product?.price_precision)}
                  </div>
                </div>
                <div className="h-10 w-px bg-gray-alpha-400" />
                <div>
                  <div className="text-label-12 text-gray-700">涨跌幅</div>
                  <div className="mt-1">
                    <PriceChange value={displayChange} />
                  </div>
                </div>
                <div className="h-10 w-px bg-gray-alpha-400" />
                <div>
                  <div className="text-label-12 text-gray-700">结算价</div>
                  <div className="mt-1 font-mono text-heading-24 font-bold text-foreground">
                    {formatPrice(displaySettle, product?.price_precision)}
                  </div>
                </div>
              </div>

              {/* 第二行：关键指标 */}
              <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
                <div className="text-center">
                  <div className="text-label-12 text-gray-700">开盘价</div>
                  <div className="mt-1 font-mono text-label-16 font-semibold text-foreground">{formatPrice(realtime?.open_price ?? product?.open_price, product?.price_precision)}</div>
                </div>
                <div className="text-center">
                  <div className="text-label-12 text-gray-700">最高</div>
                  <div className="mt-1 font-mono text-label-16 font-semibold text-up">{formatPrice(realtime?.high ?? product?.high, product?.price_precision)}</div>
                </div>
                <div className="text-center">
                  <div className="text-label-12 text-gray-700">最低</div>
                  <div className="mt-1 font-mono text-label-16 font-semibold text-down">{formatPrice(realtime?.low ?? product?.low, product?.price_precision)}</div>
                </div>
                <div className="h-6 w-px bg-gray-alpha-400" />
                <div className="text-center">
                  <div className="text-label-12 text-gray-700">成交量</div>
                  <div className="mt-1 font-mono text-label-16 font-semibold text-foreground">{formatInteger(realtime?.volume ?? product?.volume)}</div>
                </div>
                <div className="text-center">
                  <div className="text-label-12 text-gray-700">持仓量</div>
                  <div className="mt-1 font-mono text-label-16 font-semibold text-foreground">{formatInteger(realtime?.open_interest ?? product?.open_interest)}</div>
                </div>
                <div className="text-center">
                  <div className="text-label-12 text-gray-700">持仓变化</div>
                  <div className={`mt-1 font-mono text-label-16 font-semibold ${displayOiChg != null && displayOiChg > 0 ? 'text-up' : displayOiChg != null && displayOiChg < 0 ? 'text-down' : 'text-foreground'}`}>
                    {displayOiChg != null ? (displayOiChg > 0 ? `+${formatInteger(displayOiChg)}` : formatInteger(displayOiChg)) : '--'}
                  </div>
                </div>
                <div className="text-center">
                  <div className="text-label-12 text-gray-700">昨结</div>
                  <div className="mt-1 font-mono text-label-16 font-semibold text-foreground">{formatPrice(realtime?.pre_settlement ?? product?.pre_settlement, product?.price_precision)}</div>
                </div>
              </div>

              {/* 交易日期 */}
              {displayTradeDate && (
                <div className="text-label-12 text-gray-700">
                  数据日期: {displayTradeDate}
                </div>
              )}
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

              <ContractRolloverPanel rollovers={rollovers} loading={rolloversLoading} />

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

              {varietyId && (
                <PriceAlertPanel
                  displayPrice={displayPrice ?? null}
                  pricePrecision={product?.price_precision}
                  alerts={priceAlerts}
                  showForm={showAlertForm}
                  alertType={alertType}
                  alertPrice={alertPrice}
                  onToggleForm={() => setShowAlertForm((v) => !v)}
                  onChangeType={setAlertType}
                  onChangePrice={setAlertPrice}
                  onCreate={handleCreateAlert}
                  onDelete={handleDeleteAlert}
                />
              )}
            </aside>
          </div>

        </div>
      )}
    </AppShell>
  )
}

function PriceAlertPanel({
  displayPrice,
  pricePrecision,
  alerts,
  showForm,
  alertType,
  alertPrice,
  onToggleForm,
  onChangeType,
  onChangePrice,
  onCreate,
  onDelete,
}: {
  displayPrice: number | null
  pricePrecision?: number
  alerts?: PriceAlert[]
  showForm: boolean
  alertType: 'above' | 'below'
  alertPrice: string
  onToggleForm: () => void
  onChangeType: (t: 'above' | 'below') => void
  onChangePrice: (v: string) => void
  onCreate: () => void
  onDelete: (id: number) => void
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-surface p-4">
      <div className="flex items-center justify-between">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
          <Bell size={15} className="text-amber-400" />
          价格预警
        </h3>
        <button
          type="button"
          onClick={onToggleForm}
          className="inline-flex items-center gap-1 rounded-md bg-amber-500/10 px-2 py-1 text-xs font-medium text-amber-400 transition hover:bg-amber-500/20"
        >
          <Plus size={12} />
          {showForm ? '取消' : '新建'}
        </button>
      </div>

      {showForm && (
        <div className="mt-3 space-y-2">
          <div className="flex gap-2">
            {(['above', 'below'] as const).map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => onChangeType(t)}
                className={`flex-1 rounded-lg border py-1.5 text-xs transition ${
                  alertType === t
                    ? 'border-amber-500/30 bg-amber-500/10 text-amber-400'
                    : 'border-slate-700 text-slate-400 hover:border-slate-500'
                }`}
              >
                {t === 'above' ? '≥ 高于' : '≤ 低于'}
              </button>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              inputMode="decimal"
              value={alertPrice}
              onChange={(e) => onChangePrice(e.target.value)}
              placeholder={`当前 ${displayPrice != null ? formatPrice(displayPrice, pricePrecision) : '--'}`}
              className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-black/30 px-3 py-1.5 text-sm text-white placeholder-slate-500 outline-none transition focus:border-amber-500/50"
            />
            <button
              type="button"
              onClick={onCreate}
              className="shrink-0 rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-amber-500"
            >
              保存
            </button>
          </div>
        </div>
      )}

      {!alerts || alerts.length === 0 ? (
        <p className="mt-3 text-xs text-slate-500">暂无预警，设置价格提醒。</p>
      ) : (
        <div className="mt-3 space-y-2">
          {alerts.map((alert) => (
            <div
              key={alert.id}
              className="flex items-center justify-between rounded border border-slate-800 bg-black/20 p-2"
            >
              <div className="flex items-center gap-2">
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${
                    alert.alert_type === 'above'
                      ? 'bg-red-500/10 text-red-400'
                      : 'bg-green-500/10 text-green-400'
                  }`}
                >
                  {alert.alert_type === 'above' ? '≥' : '≤'}
                </span>
                <span className="text-xs text-slate-300">
                  {formatPrice(Number(alert.target_price), pricePrecision)}
                </span>
                {alert.is_triggered && (
                  <span className="rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-400">
                    已触发
                  </span>
                )}
              </div>
              <button
                type="button"
                onClick={() => onDelete(alert.id)}
                className="rounded p-1 text-slate-500 transition hover:bg-slate-800 hover:text-red-400"
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function StatePanel({ children }: { children: string }) {
  return (
    <div className="rounded border border-gray-alpha-400 bg-background p-8 text-center text-label-14 text-gray-800">
      {children}
    </div>
  )
}
