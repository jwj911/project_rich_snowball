import Link from 'next/link'
import { ReactNode } from 'react'
import { ArrowLeft } from 'lucide-react'
import PriceChange from '@/components/market/PriceChange'
import { Product, RealtimeQuote } from '@/lib/api'
import { formatInteger, formatPrice, getChangeTone, isLimitUp, isLimitDown } from '@/lib/format'

interface ProductHeaderProps {
  product: Product
  realtime: RealtimeQuote | null
  displayPrice: number | null | undefined
  displayChange: number | null | undefined
  watchlistAction?: ReactNode
}

export default function ProductHeader({
  product,
  realtime,
  displayPrice,
  displayChange,
  watchlistAction,
}: ProductHeaderProps) {
  return (
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
          {watchlistAction}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:min-w-[560px]">
        <QuoteMetric
          label="最新价"
          value={
            <span className="flex items-center gap-1.5">
              {formatPrice(displayPrice, product.price_precision)}
              {isLimitUp(displayPrice, realtime?.limit_up ?? product.limit_up) && (
                <span className="rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white">涨停</span>
              )}
              {isLimitDown(displayPrice, realtime?.limit_down ?? product.limit_down) && (
                <span className="rounded bg-green-600 px-1.5 py-0.5 text-[10px] font-bold text-white">跌停</span>
              )}
            </span>
          }
          tone={getChangeTone(displayChange)}
        />
        <QuoteMetric label="涨跌幅" value={<PriceChange value={displayChange} />} />
        <QuoteMetric label="最高" value={formatPrice(realtime?.high ?? product.high, product.price_precision)} />
        <QuoteMetric label="成交量" value={formatInteger(realtime?.volume ?? product.volume)} />
      </div>
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
