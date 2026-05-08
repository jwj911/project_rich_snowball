'use client'

import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import AppShell from '@/components/layout/AppShell'
import KlineChart from '@/components/KlineChart'
import LoginRequired from '@/components/auth/LoginRequired'
import { useAuth } from '@/components/auth/AuthProvider'
import EmptyState from '@/components/ui/EmptyState'
import ErrorState from '@/components/ui/ErrorState'
import PriceChange from '@/components/market/PriceChange'
import TechnicalAnalysisPanel from '@/components/market/TechnicalAnalysisPanel'
import { api, Comment, KlineData, Product, RealtimeQuote } from '@/lib/api'
import { formatDateTime, formatInteger, formatNumber, getChangeTone } from '@/lib/format'
import {
  ArrowLeft,
  CheckCircle2,
  CircleDollarSign,
  RefreshCw,
  Send,
  TrendingUp,
  XCircle,
} from 'lucide-react'

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
  const [supportLevels, setSupportLevels] = useState<number[]>([])
  const [resistanceLevels, setResistanceLevels] = useState<number[]>([])
  const [newSupport, setNewSupport] = useState('')
  const [newResistance, setNewResistance] = useState('')
  const [klineData, setKlineData] = useState<KlineData[]>([])
  const [realtime, setRealtime] = useState<RealtimeQuote | null>(null)
  const [levelsLoaded, setLevelsLoaded] = useState(false)

  const levelsStorageKey = useMemo(() => {
    if (!Number.isFinite(productId) || !user) return null
    return `price-levels:v1:${user.id}:${productId}`
  }, [productId, user])

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
        const [kline, quote] = await Promise.all([
          api.getKline(data.product.symbol, '1h', 80).catch(() => []),
          api.getRealtime(data.product.symbol).catch(() => null),
        ])
        setKlineData(kline)
        setRealtime(quote)
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
      try {
        const data = await api.getProduct(productId)
        setProduct(data.product)
        if (data.product?.symbol) {
          const quote = await api.getRealtime(data.product.symbol)
          setRealtime(quote)
        }
      } catch {
        // 详情页轮询失败时保留当前画面，避免打断阅读。
      }
    }, 30000)

    return () => clearInterval(interval)
  }, [authLoading, isAuthenticated, loadData, productId])

  useEffect(() => {
    setLevelsLoaded(false)

    if (!levelsStorageKey || typeof window === 'undefined') {
      setSupportLevels([])
      setResistanceLevels([])
      setLevelsLoaded(true)
      return
    }

    try {
      const rawLevels = window.localStorage.getItem(levelsStorageKey)
      if (!rawLevels) {
        setSupportLevels([])
        setResistanceLevels([])
        return
      }

      const parsed = JSON.parse(rawLevels) as {
        supportLevels?: unknown
        resistanceLevels?: unknown
      }

      const savedSupport = Array.isArray(parsed.supportLevels)
        ? parsed.supportLevels.filter(Number.isFinite)
        : []
      const savedResistance = Array.isArray(parsed.resistanceLevels)
        ? parsed.resistanceLevels.filter(Number.isFinite)
        : []

      setSupportLevels(savedSupport.sort((a, b) => a - b))
      setResistanceLevels(savedResistance.sort((a, b) => b - a))
    } catch {
      setSupportLevels([])
      setResistanceLevels([])
    } finally {
      setLevelsLoaded(true)
    }
  }, [levelsStorageKey])

  useEffect(() => {
    if (!levelsLoaded || !levelsStorageKey || typeof window === 'undefined') return

    window.localStorage.setItem(
      levelsStorageKey,
      JSON.stringify({
        supportLevels,
        resistanceLevels,
        updatedAt: new Date().toISOString(),
      }),
    )
  }, [levelsLoaded, levelsStorageKey, resistanceLevels, supportLevels])

  const displayPrice = realtime?.current_price ?? product?.current_price
  const displayChange = realtime?.change_percent ?? product?.change_percent
  const marginCost = product?.margin != null && displayPrice != null ? displayPrice * product.margin / 100 : null

  const sortedSupportLevels = useMemo(
    () => [...supportLevels].sort((a, b) => a - b),
    [supportLevels],
  )
  const sortedResistanceLevels = useMemo(
    () => [...resistanceLevels].sort((a, b) => b - a),
    [resistanceLevels],
  )

  const addSupport = (price: number) => {
    if (Number.isFinite(price) && !supportLevels.includes(price)) {
      setSupportLevels((levels) => [...levels, price].sort((a, b) => a - b))
    }
  }

  const addResistance = (price: number) => {
    if (Number.isFinite(price) && !resistanceLevels.includes(price)) {
      setResistanceLevels((levels) => [...levels, price].sort((a, b) => b - a))
    }
  }

  const submitLevel = (value: string, type: 'support' | 'resistance') => {
    const price = Number.parseFloat(value)
    if (!Number.isFinite(price)) return

    if (type === 'support') {
      addSupport(price)
      setNewSupport('')
    } else {
      addResistance(price)
      setNewResistance('')
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
                <div className="min-h-[420px]">
                  <KlineChart
                    data={klineData}
                    symbol={product.symbol}
                    supportLevels={sortedSupportLevels}
                    resistanceLevels={sortedResistanceLevels}
                    onAddSupport={addSupport}
                    onAddResistance={addResistance}
                    onRemoveSupport={(price) => setSupportLevels((levels) => levels.filter((level) => level !== price))}
                    onRemoveResistance={(price) => setResistanceLevels((levels) => levels.filter((level) => level !== price))}
                  />
                </div>

                <TechnicalAnalysisPanel
                  data={klineData}
                  currentPrice={displayPrice}
                  supportLevels={sortedSupportLevels}
                  resistanceLevels={sortedResistanceLevels}
                />

                <CommentPanel
                  comments={comments}
                  commentError={commentError}
                  isSubmitting={isSubmittingComment}
                  newComment={newComment}
                  onChangeComment={setNewComment}
                  onSubmit={handleSubmitComment}
                />
              </section>

              <aside className="space-y-5">
                <TradingInfo product={product} displayPrice={displayPrice} marginCost={marginCost} />

                <LevelEditor
                  title="支撑位"
                  icon={<CheckCircle2 size={16} className="text-green-400" />}
                  tone="support"
                  inputValue={newSupport}
                  levels={sortedSupportLevels}
                  isSaved={levelsLoaded}
                  onInputChange={setNewSupport}
                  onAdd={() => submitLevel(newSupport, 'support')}
                  onRemove={(price) => setSupportLevels((levels) => levels.filter((level) => level !== price))}
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
                  onRemove={(price) => setResistanceLevels((levels) => levels.filter((level) => level !== price))}
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
  value: string | ReactNode
  tone?: 'up' | 'down'
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-black/30 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-2 min-h-6 font-mono text-base font-semibold ${tone ?? 'text-slate-200'}`}>{value}</div>
    </div>
  )
}

function TradingInfo({
  product,
  displayPrice,
  marginCost,
}: {
  product: Product
  displayPrice: number | null | undefined
  marginCost: number | null
}) {
  return (
    <section className="rounded-lg border border-slate-800 bg-[#10161d] p-4">
      <h2 className="flex items-center gap-2 text-base font-semibold">
        <CircleDollarSign size={18} />
        交易信息
      </h2>
      <div className="mt-4 space-y-3 text-sm">
        <InfoRow label="当前价格" value={formatNumber(displayPrice)} />
        <InfoRow label="保证金率" value={product.margin != null ? `${formatNumber(product.margin)}%` : '--'} />
        <InfoRow label="预估保证金" value={formatNumber(marginCost)} valueClassName="text-green-400" />
        <InfoRow label="手续费" value={product.commission != null ? `${formatNumber(product.commission)} 元/手` : '--'} />
        <InfoRow label="更新时间" value={formatDateTime(product.updated_at)} />
      </div>
    </section>
  )
}

function InfoRow({ label, value, valueClassName = 'text-white' }: { label: string; value: string; valueClassName?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 text-slate-400">
      <span>{label}</span>
      <span className={`text-right font-mono ${valueClassName}`}>{value}</span>
    </div>
  )
}

function LevelEditor({
  title,
  icon,
  tone,
  inputValue,
  levels,
  isSaved,
  onInputChange,
  onAdd,
  onRemove,
}: {
  title: string
  icon: ReactNode
  tone: 'support' | 'resistance'
  inputValue: string
  levels: number[]
  isSaved: boolean
  onInputChange: (value: string) => void
  onAdd: () => void
  onRemove: (price: number) => void
}) {
  const isSupport = tone === 'support'
  const colorClass = isSupport ? 'text-green-400' : 'text-red-400'
  const bgClass = isSupport ? 'bg-green-400/10 hover:bg-green-400/20' : 'bg-red-400/10 hover:bg-red-400/20'
  const borderFocus = isSupport ? 'focus:border-green-500' : 'focus:border-red-500'

  return (
    <section className="rounded-lg border border-slate-800 bg-[#10161d] p-4">
      <h2 className="flex items-center gap-2 text-base font-semibold text-slate-200">
        {icon}
        {title}
      </h2>
      <div className="mt-1 text-xs text-slate-600">
        {isSaved ? '已自动保存到本机' : '正在读取本地标注...'}
      </div>
      <div className="mt-4 flex gap-2">
        <input
          type="number"
          value={inputValue}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder="价格"
          className={`min-w-0 flex-1 rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white outline-none placeholder:text-slate-600 ${borderFocus}`}
        />
        <button
          type="button"
          onClick={onAdd}
          className={`rounded-lg px-3 py-2 text-sm font-medium transition ${colorClass} ${bgClass}`}
        >
          添加
        </button>
      </div>

      <div className="mt-3 flex min-h-8 flex-wrap gap-2">
        {levels.length === 0 ? (
          <span className="text-xs text-slate-600">暂无标记</span>
        ) : (
          levels.map((level) => (
            <button
              type="button"
              key={`${tone}-${level}`}
              onClick={() => onRemove(level)}
              className={`inline-flex items-center gap-1 rounded px-2 py-1 font-mono text-xs transition ${colorClass} ${bgClass}`}
              aria-label={`删除${title} ${level.toFixed(2)}`}
            >
              {level.toFixed(2)}
              <XCircle size={12} />
            </button>
          ))
        )}
      </div>
    </section>
  )
}

function CommentPanel({
  comments,
  commentError,
  isSubmitting,
  newComment,
  onChangeComment,
  onSubmit,
}: {
  comments: Comment[]
  commentError: string | null
  isSubmitting: boolean
  newComment: string
  onChangeComment: (value: string) => void
  onSubmit: (event: FormEvent) => void
}) {
  return (
    <section className="rounded-lg border border-slate-800 bg-[#10161d] p-4">
      <h2 className="flex items-center gap-2 text-base font-semibold text-slate-200">
        <Send size={17} />
        评论区
      </h2>

      <form onSubmit={onSubmit} className="mt-4 flex flex-col gap-2 sm:flex-row">
        <input
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
