import { ReactNode } from 'react'

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
  default: 'text-slate-200',
  muted: 'text-slate-400',
  up: 'text-red-400',
  down: 'text-green-400',
  warning: 'text-amber-300',
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
    <div className={`rounded-lg border border-slate-800 bg-black/30 p-3 ${className}`}>
      <div className="flex items-center gap-1.5 text-xs text-slate-500">
        {icon}
        <span>{label}</span>
      </div>
      <div className={`mt-2 truncate font-mono font-semibold ${sizeClass[size]} ${toneClass[tone]}`}>
        {value}
      </div>
    </div>
  )
}
