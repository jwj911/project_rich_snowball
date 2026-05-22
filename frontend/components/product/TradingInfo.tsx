'use client'

import { useEffect, useState } from 'react'
import { CircleDollarSign } from 'lucide-react'
import { api, Product } from '@/lib/api'
import { formatDateTime, formatNumber, formatPrice } from '@/lib/format'

interface TradingInfoProps {
  product: Product
  displayPrice: number | null | undefined
}

export default function TradingInfo({ product, displayPrice }: TradingInfoProps) {
  const [fees, setFees] = useState<{
    margin_rate: number | null
    margin_amount: number | null
    commission_open: number | null
    commission_close: number | null
    commission_close_today: number | null
    unit: string | null
    updated_at: string | null
  } | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api.getVarietyFees(product.symbol)
      .then((data) => {
        if (!cancelled) setFees(data)
      })
      .catch(() => {
        // 静默失败，仍展示 product 的保底数据
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [product.symbol])

  const marginRate = fees?.margin_rate ?? (product.margin != null ? product.margin / 100 : null)
  const marginCost = marginRate != null && displayPrice != null ? displayPrice * marginRate : null
  const commissionOpen = fees?.commission_open ?? product.commission

  return (
    <section className="rounded-lg border border-slate-800 bg-[#10161d] p-4">
      <h2 className="flex items-center gap-2 text-base font-semibold">
        <CircleDollarSign size={18} />
        交易信息
        {loading && <span className="ml-auto text-xs text-slate-500">加载中...</span>}
      </h2>
      <div className="mt-4 space-y-3 text-sm">
        <InfoRow label="当前价格" value={formatPrice(displayPrice, product.price_precision)} />
        <InfoRow label="保证金率" value={marginRate != null ? `${formatNumber(marginRate * 100)}%` : '--'} />
        <InfoRow label="预估保证金" value={formatPrice(marginCost, product.price_precision)} valueClassName="text-green-400" />
        <InfoRow label="开仓手续费" value={commissionOpen != null ? `${formatNumber(commissionOpen)} 元/手` : '--'} />
        {fees?.commission_close_today != null && (
          <InfoRow label="平今手续费" value={`${formatNumber(fees.commission_close_today)} 元/手`} />
        )}
        {fees?.unit && <InfoRow label="交易单位" value={fees.unit} />}
        <InfoRow label="更新时间" value={formatDateTime(fees?.updated_at ?? product.updated_at)} />
      </div>
    </section>
  )
}

function InfoRow({ label, value, valueClassName = 'text-white' }: { label: string; value: string; valueClassName?: string }) {
  return (
    <div className="flex items-center justify-between gap-3 text-slate-400">
      <span>{label}</span>
      <span className={`text-right font-mono ${valueClassName}`}>{value}</span>
    </div>
  )
}
