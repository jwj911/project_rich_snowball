import { CircleDollarSign } from 'lucide-react'
import { Product } from '@/lib/api'
import { formatDateTime, formatInteger, formatNumber, formatPrice } from '@/lib/format'

interface TradingInfoPanelProps {
  product: Product
  displayPrice: number | null | undefined
  marginCost: number | null
}

export default function TradingInfoPanel({ product, displayPrice, marginCost }: TradingInfoPanelProps) {
  return (
    <section className="rounded-lg border border-slate-800 bg-surface p-4">
      <h2 className="flex items-center gap-2 text-base font-semibold">
        <CircleDollarSign size={18} />
        交易信息
      </h2>
      <div className="mt-4 space-y-3 text-sm">
        <InfoRow label="当前价格" value={formatPrice(displayPrice, product.price_precision)} />
        <InfoRow label="交易所" value={product.exchange ?? '--'} />
        <InfoRow label="合约代码" value={product.contract_code ?? '--'} />
        <InfoRow label="最小变动价位" value={product.tick_size != null ? formatPrice(Number(product.tick_size), product.price_precision) : '--'} />
        <InfoRow label="保证金率" value={product.margin != null ? `${formatNumber(product.margin)}%` : '--'} />
        <InfoRow label="预估保证金" value={formatPrice(marginCost, product.price_precision)} valueClassName="text-green-400" />
        <InfoRow label="手续费" value={product.commission != null ? `${formatNumber(product.commission)} 元/手` : '--'} />
        <InfoRow label="涨停" value={formatPrice(product.limit_up, product.price_precision)} valueClassName="text-red-400" />
        <InfoRow label="跌停" value={formatPrice(product.limit_down, product.price_precision)} valueClassName="text-green-400" />
        {product.bid1 != null && (
          <InfoRow label="买一" value={formatPrice(product.bid1, product.price_precision)} valueClassName="text-red-300" />
        )}
        {product.ask1 != null && (
          <InfoRow label="卖一" value={formatPrice(product.ask1, product.price_precision)} valueClassName="text-green-300" />
        )}
        {product.open_interest != null && (
          <InfoRow label="持仓量" value={formatInteger(product.open_interest)} />
        )}
        {product.pre_settlement != null && (
          <InfoRow label="昨结" value={formatPrice(product.pre_settlement, product.price_precision)} />
        )}
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
