import Link from 'next/link'
import EmptyState from '@/components/ui/EmptyState'
import PriceChange from '@/components/market/PriceChange'
import { Product } from '@/lib/api'
import { formatNumber } from '@/lib/format'
import { Star } from 'lucide-react'

export default function WatchlistPanel({ products }: { products: Product[] }) {
  const previewProducts = products.slice(0, 4)

  return (
    <section className="rounded-lg border border-slate-800 bg-[#10161d] p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">自选观察</h2>
          <p className="mt-1 text-xs text-slate-500">后续接入自选 API 前，先展示活跃品种入口。</p>
        </div>
        <span className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-500">占位</span>
      </div>

      {previewProducts.length === 0 ? (
        <EmptyState
          icon={Star}
          title="暂无可观察品种"
          description="行情数据加载后，这里会展示常用入口；后续将替换为真实自选。"
          className="mt-4 bg-black/20"
        />
      ) : (
        <div className="mt-4 space-y-2">
          {previewProducts.map((product) => (
            <Link
              key={product.id}
              href={`/products/${product.id}`}
              className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-black/20 px-3 py-2 transition hover:border-red-800/80 hover:bg-[#121b24]"
            >
              <div className="min-w-0">
                <div className="truncate text-sm font-medium text-white">{product.name}</div>
                <div className="mt-0.5 font-mono text-xs text-slate-500">{product.symbol}</div>
              </div>
              <div className="text-right">
                <div className="font-mono text-sm text-slate-200">{formatNumber(product.current_price)}</div>
                <PriceChange value={product.change_percent} className="text-xs" />
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}
