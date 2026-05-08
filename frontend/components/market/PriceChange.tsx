import { TrendingDown, TrendingUp } from 'lucide-react'
import { formatPercent, getChangeTone } from '@/lib/format'

interface PriceChangeProps {
  value: number | null | undefined
  showIcon?: boolean
  className?: string
}

export default function PriceChange({ value, showIcon = true, className = '' }: PriceChangeProps) {
  const isUp = (value ?? 0) >= 0
  const Icon = isUp ? TrendingUp : TrendingDown

  return (
    <span className={`inline-flex items-center gap-1 font-mono ${getChangeTone(value)} ${className}`}>
      {showIcon && <Icon size={14} />}
      {formatPercent(value)}
    </span>
  )
}
