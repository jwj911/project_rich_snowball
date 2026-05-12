import Link from 'next/link'
import { ArrowRight, ArrowUpDown } from 'lucide-react'
import PriceChange from '@/components/market/PriceChange'
import QuoteCard from '@/components/market/QuoteCard'
import { Product } from '@/lib/api'
import { formatDateTime, formatInteger, formatNumber, getChangeTone } from '@/lib/format'

export type QuoteSortField = 'change_percent' | 'volume' | 'current_price'
export type QuoteSortOrder = 'asc' | 'desc'

interface QuoteTableProps {
  products: Product[]
  sortBy: QuoteSortField
  sortOrder: QuoteSortOrder
  onSort: (field: QuoteSortField) => void
}

export default function QuoteTable({ products, sortBy, sortOrder, onSort }: QuoteTableProps) {
  const SortButton = ({ field, label }: { field: QuoteSortField; label: string }) => (
    <button
      type="button"
      onClick={() => onSort(field)}
      className={`inline-flex items-center justify-end gap-1 text-sm transition-colors hover:text-white ${
        sortBy === field ? 'text-red-400' : 'text-slate-400'
      }`}
    >
      {label}
      <ArrowUpDown size={14} className={sortBy === field && sortOrder === 'asc' ? 'rotate-180' : ''} />
    </button>
  )

  return (
    <>
      <div className="grid gap-3 md:hidden">
        {products.map((product) => (
          <QuoteCard key={product.id} product={product} />
        ))}
      </div>

      <div className="hidden overflow-hidden rounded-lg border border-slate-800 bg-[#10161d] md:block">
        <table className="w-full table-fixed">
          <thead>
            <tr className="border-b border-slate-800 bg-black/20">
              <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">品种</th>
              <th className="px-4 py-3 text-right"><SortButton field="current_price" label="最新价" /></th>
              <th className="px-4 py-3 text-right"><SortButton field="change_percent" label="涨跌幅" /></th>
              <th className="px-4 py-3 text-right"><SortButton field="volume" label="成交量" /></th>
              <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">更新时间</th>
              <th className="w-24 px-4 py-3 text-right text-sm font-medium text-slate-400">操作</th>
            </tr>
          </thead>
          <tbody>
            {products.map((product) => {
              const tone = getChangeTone(product.change_percent)

              return (
                <tr key={product.id} className="border-b border-slate-800/80 transition-colors last:border-0 hover:bg-slate-900/60">
                  <td className="px-4 py-3">
                    <div className="min-w-0">
                      <div className="truncate font-medium text-white">{product.name}</div>
                      <div className="mt-1 font-mono text-xs text-slate-500">{product.symbol}</div>
                    </div>
                  </td>
                  <td className={`px-4 py-3 text-right font-mono font-semibold ${tone}`}>
                    {formatNumber(product.current_price)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <PriceChange value={product.change_percent} className="justify-end" />
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-slate-300">
                    {formatInteger(product.volume)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-sm text-slate-400">
                    {formatDateTime(product.updated_at)}
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      href={`/products/${product.id}`}
                      className="inline-flex items-center justify-end gap-1 text-sm text-red-400 transition-colors hover:text-red-300"
                    >
                      详情
                      <ArrowRight size={14} />
                    </Link>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}
