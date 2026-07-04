import Link from 'next/link'
import { ReactNode } from 'react'
import { ArrowLeft } from 'lucide-react'
import Card from '@/components/ui/Card'
import Badge from '@/components/ui/Badge'
import MetricCard from '@/components/ui/MetricCard'
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
  const isUpLimit = isLimitUp(displayPrice, realtime?.limit_up ?? product.limit_up)
  const isDownLimit = isLimitDown(displayPrice, realtime?.limit_down ?? product.limit_down)
  const priceTone = getChangeTone(displayChange)
  const metricTone: 'default' | 'up' | 'down' = priceTone === 'neutral' ? 'default' : priceTone

  return (
    <Card>
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <Link
            href="/products"
            className="inline-flex items-center gap-2 text-label-14 text-gray-700 transition hover:text-foreground"
          >
            <ArrowLeft size={15} />
            返回行情中心
          </Link>
          <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-2">
            <h1 className="text-heading-24 text-foreground">{product.name}</h1>
            <span className="font-mono text-label-14 text-gray-700">{product.symbol}</span>
            {product.category && (
              <Badge variant="secondary">{product.category}</Badge>
            )}
            {isUpLimit && <Badge variant="market-up">涨停</Badge>}
            {isDownLimit && <Badge variant="market-down">跌停</Badge>}
            {watchlistAction}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:min-w-[560px]">
          <MetricCard
            label="最新价"
            value={formatPrice(displayPrice, product.price_precision)}
            tone={metricTone}
          />
          <MetricCard label="涨跌幅" value={<PriceChange value={displayChange} />} />
          <MetricCard label="最高" value={formatPrice(realtime?.high ?? product.high, product.price_precision)} />
          <MetricCard label="成交量" value={formatInteger(realtime?.volume ?? product.volume)} />
        </div>
      </div>
    </Card>
  )
}
