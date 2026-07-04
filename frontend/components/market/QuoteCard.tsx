import Link from 'next/link'
import { ArrowRight } from 'lucide-react'
import PriceChange from '@/components/market/PriceChange'
import PriceFlash from '@/components/market/PriceFlash'
import Badge from '@/components/ui/Badge'
import { Product } from '@/lib/api'
import { formatDateTime, formatInteger, formatPrice, getChangeTone, isLimitUp, isLimitDown } from '@/lib/format'
import { memo } from 'react'

interface QuoteCardProps {
  product: Product
}

function QuoteCard({ product }: QuoteCardProps) {
  const tone = getChangeTone(product.change_percent)

  return (
    <Link
      href={`/products/${product.symbol}`}
      className="group block rounded border border-gray-alpha-400 bg-background p-4 transition hover:border-gray-alpha-500 hover:bg-gray-100"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="truncate text-heading-14 text-foreground">{product.name}</h2>
            <span className="shrink-0 font-mono text-label-12 text-gray-700">{product.symbol}</span>
          </div>
          <div className="mt-1 text-label-12 text-gray-700">{product.category || '期货品种'}</div>
        </div>
        <ArrowRight size={16} className="mt-1 shrink-0 text-gray-600 transition group-hover:text-foreground" />
      </div>

      <div className="mt-4 flex items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-1.5">
            <PriceFlash value={product.current_price} className={`inline-block font-mono text-2xl font-bold ${tone}`}>
              {formatPrice(product.current_price, product.price_precision)}
            </PriceFlash>
            {isLimitUp(product.current_price, product.limit_up) && (
              <Badge variant="market-up">涨停</Badge>
            )}
            {isLimitDown(product.current_price, product.limit_down) && (
              <Badge variant="market-down">跌停</Badge>
            )}
          </div>
          <PriceChange value={product.change_percent} className="mt-1 text-sm" />
        </div>
        <div className="text-right text-label-12 text-gray-700">
          <div>高 <span className="font-mono text-foreground">{formatPrice(product.high, product.price_precision)}</span></div>
          <div>低 <span className="font-mono text-foreground">{formatPrice(product.low, product.price_precision)}</span></div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-gray-alpha-400 pt-3 text-label-12 text-gray-700">
        <div>
          <div>成交量</div>
          <div className="mt-1 font-mono text-foreground">{formatInteger(product.volume)}</div>
        </div>
        <div className="text-right">
          <div>更新</div>
          <div className="mt-1 font-mono text-foreground">{formatDateTime(product.updated_at)}</div>
        </div>
      </div>
    </Link>
  )
}

export default memo(QuoteCard)
