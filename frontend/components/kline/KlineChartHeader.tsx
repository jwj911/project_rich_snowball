import { formatPrice } from '@/lib/format'
import { CandlePoint, CrosshairQuote, maxOf, minOf } from '@/lib/klineChart'

interface KlineChartHeaderProps {
  symbol: string
  points: CandlePoint[]
  firstPoint: CandlePoint
  latestPoint: CandlePoint
  quote: CrosshairQuote | null
  pricePrecision?: number
}

export default function KlineChartHeader({
  symbol,
  points,
  firstPoint,
  latestPoint,
  quote,
  pricePrecision = 2,
}: KlineChartHeaderProps) {
  const latestColor = latestPoint.close >= firstPoint.open ? 'text-red-400' : 'text-green-400'

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border px-3 py-2 text-xs text-slate-400">
      <span className="mr-auto font-semibold text-white">{symbol}</span>
      <span>
        最新 <span className={`font-mono ${latestColor}`}>{formatPrice(latestPoint.close, pricePrecision)}</span>
      </span>
      <span>开 <span className="font-mono text-slate-200">{formatPrice(quote?.open ?? firstPoint.open, pricePrecision)}</span></span>
      <span>高 <span className="font-mono text-red-300">{formatPrice(quote?.high ?? maxOf(points, 'high'), pricePrecision)}</span></span>
      <span>低 <span className="font-mono text-green-300">{formatPrice(quote?.low ?? minOf(points, 'low'), pricePrecision)}</span></span>
    </div>
  )
}
