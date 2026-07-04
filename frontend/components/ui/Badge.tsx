import { ReactNode } from 'react'

export type BadgeVariant =
  | 'default'
  | 'secondary'
  | 'success'
  | 'warning'
  | 'danger'
  | 'market-up'
  | 'market-down'

interface BadgeProps {
  children: ReactNode
  variant?: BadgeVariant
  className?: string
}

const variantClasses: Record<BadgeVariant, string> = {
  default: 'border-gray-alpha-400 bg-gray-alpha-100 text-foreground',
  secondary: 'border-gray-alpha-400 bg-background text-gray-900',
  success: 'border-green-900/40 bg-green-100 text-green-900',
  warning: 'border-amber-900/40 bg-amber-100 text-amber-700',
  danger: 'border-red-900/40 bg-red-100 text-red-900',
  'market-up': 'border-red-900/40 bg-red-100 text-red-700',
  'market-down': 'border-green-900/40 bg-green-100 text-green-700',
}

export default function Badge({ children, variant = 'default', className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-xs font-medium ${variantClasses[variant]} ${className}`}
    >
      {children}
    </span>
  )
}
