import { CircleDollarSign } from 'lucide-react'
import { Product } from '@/lib/api'
import { formatDateTime, formatNumber, formatPrice } from '@/lib/format'

interface TradingInfoPanelProps {
  product: Product
  displayPrice: number | null | undefined
  marginCost: number | null
}

export default function TradingInfoPanel({ product, displayPrice, marginCost }: TradingInfoPanelProps) {
  return (
    <section className="rounded-lg border border-slate-800 bg-[#10161d] p-4">
      <h2 className="flex items-center gap-2 text-base font-semibold">
        <CircleDollarSign size={18} />
        交易信息
      </h2>
      <div className="mt-4 space-y-3 text-sm">
        <InfoRow label="当前价格" value={formatPrice(displayPrice, product.price_precision)} />
        <InfoRow label="保证金率" value={product.margin != null ? `${formatNumber(product.margin)}%` : '--'} />
        <InfoRow label="预估保证金" value={formatPrice(marginCost, product.price_precision)} valueClassName="text-green-400" />
        <InfoRow label="手续费" value={product.commission != null ? `${formatNumber(product.commission)} 元/手` : '--'} />
        <InfoRow label="更新时间" value={formatDateTime(product.updated_at)} />
      </div>
    </section>
  )
}

function InfoRow({
  label,
  value,
  valueClassName = 'text-white',
}: {
  label: string
  value: string
  valueClassName?: string
}) {
  return (
    <div className="flex items-center justify-between gap-3 text-slate-400">
      <span>{label}</span>
      <span className={`text-right font-mono ${valueClassName}`}>{value}</span>
    </div>
  )
}
