import { ReactNode } from 'react'
import Card from './Card'

type MetricTone = 'default' | 'muted' | 'up' | 'down' | 'warning'
type MetricSize = 'sm' | 'md' | 'lg'

interface MetricCardProps {
  label: string
  value: ReactNode
  tone?: MetricTone
  size?: MetricSize
  icon?: ReactNode
  className?: string
}

const toneClass: Record<MetricTone, string> = {
  default: 'text-foreground',
  muted: 'text-gray-900',
  up: 'text-up',
  down: 'text-down',
  warning: 'text-amber-700',
}

const sizeClass: Record<MetricSize, string> = {
  sm: 'text-base',
  md: 'text-xl',
  lg: 'text-2xl',
}

export default function MetricCard({
  label,
  value,
  tone = 'default',
  size = 'md',
  icon,
  className = '',
}: MetricCardProps) {
  return (
    <Card padding="sm" className={`border-gray-alpha-400 bg-gray-100 ${className}`}>
      <div className="flex items-center gap-1.5 text-label-12 text-gray-800">
        {icon}
        <span>{label}</span>
      </div>
      <div className={`mt-2 truncate font-mono font-semibold ${sizeClass[size]} ${toneClass[tone]}`}>
        {value}
      </div>
    </Card>
  )
}
