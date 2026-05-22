import Link from 'next/link'
import EmptyState from '@/components/ui/EmptyState'
import PriceChange from '@/components/market/PriceChange'
import { Product, Watchlist, RealtimeQuote } from '@/lib/api'
import { formatPrice } from '@/lib/format'
import { Star, Trash2, Zap } from 'lucide-react'

interface WatchlistPanelProps {
  watchlists: Watchlist[]
  products: Product[]
  realtimeQuotes?: Map<string, RealtimeQuote>
  onDelete?: (id: number) => void
}

export default function WatchlistPanel({ watchlists, products, realtimeQuotes, onDelete }: WatchlistPanelProps) {
  const productMap = new Map(products.map((p) => [p.symbol, p]))
  const hasRealtime = realtimeQuotes && realtimeQuotes.size > 0

  return (
    <section className="rounded-lg border border-slate-800 bg-[#10161d] p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">自选观察</h2>
          <p className="mt-1 text-xs text-slate-500">
            {watchlists.length === 0 ? '添加自选品种，快速跟踪关注标的。' : `已关注 ${watchlists.length} 个品种`}
          </p>
        </div>
        {hasRealtime && (
          <span title="实时行情中">
            <Zap size={14} className="animate-pulse text-amber-400" />
          </span>
        )}
      </div>

      {watchlists.length === 0 ? (
        <EmptyState
          icon={Star}
          title="暂无自选品种"
          description="进入品种详情页点击“加入自选”，即可在这里跟踪关注标的。"
          className="mt-4 bg-black/20"
        />
      ) : (
        <div className="mt-4 space-y-2">
          {watchlists.map((item) => {
            const product = productMap.get(item.variety_symbol)
            const realtime = realtimeQuotes?.get(item.variety_symbol)
            const displayPrice = realtime?.current_price ?? product?.current_price
            const displayChange = realtime?.change_percent ?? product?.change_percent
            return (
              <div
                key={item.id}
                className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-black/20 px-3 py-2 transition hover:border-red-800/80 hover:bg-[#121b24]"
              >
                <Link
                  href={`/products/${product?.id ?? 0}`}
                  className="flex min-w-0 flex-1 items-center justify-between gap-3"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-white">{item.variety_name}</div>
                    <div className="mt-0.5 flex items-center gap-1.5">
                      <span className="font-mono text-xs text-slate-500">{item.variety_symbol}</span>
                      {realtime && (
                      <span className="inline-flex items-center gap-0.5 rounded bg-amber-500/10 px-1 py-0.5 text-[10px] font-medium text-amber-400">
                        <Zap size={8} />
                        实时
                      </span>
                    )}
                    </div>
                  </div>
                  {(displayPrice != null) && (
                    <div className="text-right">
                      <div className="font-mono text-sm text-slate-200">{formatPrice(displayPrice, product?.price_precision)}</div>
                      <PriceChange value={displayChange} className="text-xs" />
                    </div>
                  )}
                </Link>
                {onDelete && (
                  <button
                    type="button"
                    onClick={() => onDelete(item.id)}
                    className="rounded p-1 text-slate-600 transition hover:bg-red-500/10 hover:text-red-400"
                    title="删除自选"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
