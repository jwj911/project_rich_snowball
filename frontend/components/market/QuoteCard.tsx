import Link from 'next/link'
import { ArrowRight } from 'lucide-react'
import PriceChange from '@/components/market/PriceChange'
import PriceFlash from '@/components/market/PriceFlash'
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
      className="group block rounded-lg border border-slate-800 bg-surface p-4 transition hover:border-red-800/80 hover:bg-[#121b24]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <h2 className="truncate text-base font-semibold text-white">{product.name}</h2>
            <span className="shrink-0 font-mono text-xs text-slate-500">{product.symbol}</span>
          </div>
          <div className="mt-1 text-xs text-slate-500">{product.category || '期货品种'}</div>
        </div>
        <ArrowRight size={16} className="mt-1 shrink-0 text-slate-600 transition group-hover:text-red-400" />
      </div>

      <div className="mt-4 flex items-end justify-between gap-3">
        <div>
          <div className="flex items-center gap-1.5">
            <PriceFlash value={product.current_price} className={`inline-block font-mono text-2xl font-bold ${tone}`}>
              {formatPrice(product.current_price, product.price_precision)}
            </PriceFlash>
            {isLimitUp(product.current_price, product.limit_up) && (
              <span className="rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white">涨停</span>
            )}
            {isLimitDown(product.current_price, product.limit_down) && (
              <span className="rounded bg-green-600 px-1.5 py-0.5 text-[10px] font-bold text-white">跌停</span>
            )}
          </div>
          <PriceChange value={product.change_percent} className="mt-1 text-sm" />
        </div>
        <div className="text-right text-xs text-slate-500">
          <div>高 <span className="font-mono text-slate-300">{formatPrice(product.high, product.price_precision)}</span></div>
          <div>低 <span className="font-mono text-slate-300">{formatPrice(product.low, product.price_precision)}</span></div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 border-t border-slate-800 pt-3 text-xs text-slate-500">
        <div>
          <div>成交量</div>
          <div className="mt-1 font-mono text-slate-300">{formatInteger(product.volume)}</div>
        </div>
        <div className="text-right">
          <div>更新</div>
          <div className="mt-1 font-mono text-slate-300">{formatDateTime(product.updated_at)}</div>
        </div>
      </div>
    </Link>
  )
}

export default memo(QuoteCard)
