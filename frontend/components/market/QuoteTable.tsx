import Link from 'next/link'
import { ArrowRight, ArrowUpDown } from 'lucide-react'
import PriceChange from '@/components/market/PriceChange'
import PriceFlash from '@/components/market/PriceFlash'
import QuoteCard from '@/components/market/QuoteCard'
import Badge from '@/components/ui/Badge'
import Card from '@/components/ui/Card'
import { Product } from '@/lib/api'
import { formatDateTime, formatInteger, formatPrice, getChangeTone } from '@/lib/format'
import { memo } from 'react'

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
      className={`inline-flex items-center justify-end gap-1 text-label-13 transition-colors hover:text-foreground ${
        sortBy === field ? 'text-foreground' : 'text-gray-700'
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

      <Card padding="none" className="hidden overflow-hidden md:block">
        <table className="w-full table-fixed">
          <thead>
            <tr className="border-b border-gray-alpha-400 bg-gray-100">
              <th className="px-4 py-3 text-left text-label-13 text-gray-700">品种</th>
              <th className="px-4 py-3 text-right"><SortButton field="current_price" label="最新价" /></th>
              <th className="px-4 py-3 text-right"><SortButton field="change_percent" label="涨跌幅" /></th>
              <th className="px-4 py-3 text-right"><SortButton field="volume" label="成交量" /></th>
              <th className="px-4 py-3 text-right text-label-13 text-gray-700">更新时间</th>
              <th className="w-24 px-4 py-3 text-right text-label-13 text-gray-700">操作</th>
            </tr>
          </thead>
          <tbody>
            {products.map((product) => (
              <QuoteRow key={product.id} product={product} />
            ))}
          </tbody>
        </table>
      </Card>
    </>
  )
}

const QuoteRow = memo(function QuoteRow({ product }: { product: Product }) {
  const tone = getChangeTone(product.change_percent)

  return (
    <tr className="border-b border-gray-alpha-400 transition-colors last:border-0 hover:bg-gray-alpha-100">
      <td className="px-4 py-3">
        <div className="min-w-0">
          <div className="truncate font-medium text-foreground">{product.name}</div>
          <div className="mt-1 font-mono text-label-12 text-gray-700">{product.symbol}</div>
        </div>
      </td>
      <td className="px-4 py-3 text-right">
        <div className="flex items-center justify-end gap-1.5">
          <PriceFlash value={product.current_price} className={`inline-block font-mono font-semibold ${tone}`}>
            {formatPrice(product.current_price, product.price_precision)}
          </PriceFlash>
          {product.limit_up != null && Math.abs((product.current_price ?? 0) - product.limit_up) < 0.01 && (
            <Badge variant="market-up">涨停</Badge>
          )}
          {product.limit_down != null && Math.abs((product.current_price ?? 0) - product.limit_down) < 0.01 && (
            <Badge variant="market-down">跌停</Badge>
          )}
        </div>
      </td>
      <td className="px-4 py-3 text-right">
        <PriceChange value={product.change_percent} className="justify-end" />
      </td>
      <td className="px-4 py-3 text-right font-mono text-foreground">
        {formatInteger(product.volume)}
      </td>
      <td className="px-4 py-3 text-right font-mono text-label-13 text-gray-700">
        {formatDateTime(product.updated_at)}
      </td>
      <td className="px-4 py-3 text-right">
        <Link
          href={`/products/${product.symbol}`}
          className="inline-flex items-center justify-end gap-1 text-label-13 text-gray-700 transition-colors hover:text-foreground"
        >
          详情
          <ArrowRight size={14} />
        </Link>
      </td>
    </tr>
  )
})
