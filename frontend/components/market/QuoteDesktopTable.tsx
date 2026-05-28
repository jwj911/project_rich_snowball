import Link from 'next/link'
import { memo } from 'react'
import { ArrowRight, ArrowUpDown } from 'lucide-react'
import PriceChange from '@/components/market/PriceChange'
import PriceFlash from '@/components/market/PriceFlash'
import { Product } from '@/lib/api'
import { formatDateTime, formatInteger, formatPrice, getChangeTone } from '@/lib/format'
import type { QuoteSortField, QuoteSortOrder } from '@/components/market/types'

interface QuoteDesktopTableProps {
  products: Product[]
  sortBy: QuoteSortField
  sortOrder: QuoteSortOrder
  onSort: (field: QuoteSortField) => void
}

export default function QuoteDesktopTable({
  products,
  sortBy,
  sortOrder,
  onSort,
}: QuoteDesktopTableProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-800 bg-surface">
      <table className="w-full table-fixed">
        <thead>
          <tr className="border-b border-slate-800 bg-black/20">
            <th className="px-4 py-3 text-left text-sm font-medium text-slate-400">品种</th>
            <SortableHeader field="current_price" label="最新价" sortBy={sortBy} sortOrder={sortOrder} onSort={onSort} />
            <SortableHeader field="change_percent" label="涨跌幅" sortBy={sortBy} sortOrder={sortOrder} onSort={onSort} />
            <SortableHeader field="volume" label="成交量" sortBy={sortBy} sortOrder={sortOrder} onSort={onSort} />
            <th className="px-4 py-3 text-right text-sm font-medium text-slate-400">更新时间</th>
            <th className="w-24 px-4 py-3 text-right text-sm font-medium text-slate-400">操作</th>
          </tr>
        </thead>
        <tbody>
          {products.map((product) => (
            <QuoteRow key={product.id} product={product} />
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SortableHeader({
  field,
  label,
  sortBy,
  sortOrder,
  onSort,
}: {
  field: QuoteSortField
  label: string
  sortBy: QuoteSortField
  sortOrder: QuoteSortOrder
  onSort: (field: QuoteSortField) => void
}) {
  const isActive = sortBy === field

  return (
    <th
      className="px-4 py-3 text-right"
      aria-sort={isActive ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'}
      scope="col"
    >
      <button
        type="button"
        onClick={() => onSort(field)}
        className={`inline-flex items-center justify-end gap-1 text-sm transition-colors hover:text-white ${
          isActive ? 'text-red-400' : 'text-slate-400'
        }`}
      >
        {label}
        <ArrowUpDown size={14} className={isActive && sortOrder === 'asc' ? 'rotate-180' : ''} />
      </button>
    </th>
  )
}

const QuoteRow = memo(function QuoteRow({ product }: { product: Product }) {
  const tone = getChangeTone(product.change_percent)

  return (
    <tr className="border-b border-slate-800/80 transition-colors last:border-0 hover:bg-slate-900/60">
      <td className="px-4 py-3">
        <div className="min-w-0">
          <div className="truncate font-medium text-white">{product.name}</div>
          <div className="mt-1 font-mono text-xs text-slate-500">{product.symbol}</div>
        </div>
      </td>
      <td className="px-4 py-3 text-right">
        <div className="flex items-center justify-end gap-1.5">
          <PriceFlash value={product.current_price} className={`inline-block font-mono font-semibold ${tone}`}>
            {formatPrice(product.current_price, product.price_precision)}
          </PriceFlash>
          {product.limit_up != null && Math.abs((product.current_price ?? 0) - product.limit_up) < 0.01 && (
            <span className="rounded bg-red-600 px-1 py-0.5 text-[10px] font-bold text-white">涨停</span>
          )}
          {product.limit_down != null && Math.abs((product.current_price ?? 0) - product.limit_down) < 0.01 && (
            <span className="rounded bg-green-600 px-1 py-0.5 text-[10px] font-bold text-white">跌停</span>
          )}
        </div>
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
          href={`/products/${product.symbol}`}
          className="inline-flex items-center justify-end gap-1 text-sm text-red-400 transition-colors hover:text-red-300"
        >
          详情
          <ArrowRight size={14} />
        </Link>
      </td>
    </tr>
  )
})
