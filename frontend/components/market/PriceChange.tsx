import { TrendingDown, TrendingUp } from 'lucide-react'
import { formatPercent, getChangeTone } from '@/lib/format'

const TONE_CLASS: Record<ReturnType<typeof getChangeTone>, string> = {
  up: 'text-up',
  down: 'text-down',
  neutral: 'text-gray-800',
}

interface PriceChangeProps {
  value: number | null | undefined
  showIcon?: boolean
  className?: string
}

export default function PriceChange({ value, showIcon = true, className = '' }: PriceChangeProps) {
  const tone = getChangeTone(value)
  const Icon = tone === 'up' ? TrendingUp : TrendingDown

  return (
    <span className={`inline-flex items-center gap-1 font-mono ${TONE_CLASS[tone]} ${className}`}>
      {showIcon && tone !== 'neutral' && <Icon size={14} />}
      {formatPercent(value)}
    </span>
  )
}
