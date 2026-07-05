import { formatPrice } from '@/lib/format'
import { CandlePoint, CrosshairQuote } from '@/lib/klineChart'

interface CrosshairTooltipProps {
  quote: CrosshairQuote | null
  latestPoint: CandlePoint
  pricePrecision?: number
}

function formatKlineDate(time: string): string {
  const date = new Date(time)
  if (Number.isNaN(date.getTime())) return time
  const y = date.getUTCFullYear()
  const m = String(date.getUTCMonth() + 1).padStart(2, '0')
  const d = String(date.getUTCDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export default function CrosshairTooltip({ quote, latestPoint, pricePrecision = 2 }: CrosshairTooltipProps) {
  const contractCode = quote?.contractCode ?? latestPoint.contractCode
  const displayTime = quote?.time ? formatKlineDate(quote.time) : formatKlineDate(latestPoint.originalTime)

  return (
    <div className="absolute left-3 top-12 rounded border border-border bg-surface-elevated/95 px-3 py-2 text-xs shadow-lg">
      <div className="grid grid-cols-[42px_minmax(72px,auto)] gap-x-3 gap-y-1">
        <span className="text-slate-500">时间</span>
        <span className="font-mono text-slate-200">{displayTime}</span>
        <span className="text-slate-500">收盘</span>
        <span className="font-mono text-slate-200">{formatPrice(quote?.close ?? latestPoint.close, pricePrecision)}</span>
        <span className="text-slate-500">成交量</span>
        <span className="font-mono text-slate-200">{Math.round(quote?.volume ?? latestPoint.volume).toLocaleString()}</span>
        {contractCode && (
          <>
            <span className="text-slate-500">合约</span>
            <span className="font-mono text-slate-200">{contractCode}</span>
          </>
        )}
      </div>
    </div>
  )
}
