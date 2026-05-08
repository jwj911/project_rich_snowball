import { LucideIcon } from 'lucide-react'
import { ReactNode } from 'react'

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  action?: ReactNode
  className?: string
}

export default function EmptyState({ icon: Icon, title, description, action, className = '' }: EmptyStateProps) {
  return (
    <div className={`rounded-lg border border-slate-800 bg-black p-8 text-center ${className}`}>
      {Icon && <Icon size={42} className="mx-auto mb-4 text-slate-600" />}
      <h2 className="mb-2 text-lg font-semibold text-white">{title}</h2>
      {description && <p className="mx-auto max-w-md text-sm leading-6 text-slate-400">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
