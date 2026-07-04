import { LucideIcon } from 'lucide-react'
import { ReactNode } from 'react'
import Card from './Card'

interface EmptyStateProps {
  icon?: LucideIcon
  title: string
  description?: string
  action?: ReactNode
  className?: string
}

export default function EmptyState({ icon: Icon, title, description, action, className = '' }: EmptyStateProps) {
  return (
    <Card padding="lg" className={`text-center ${className}`}>
      {Icon && <Icon size={42} className="mx-auto mb-4 text-gray-600" />}
      <h2 className="mb-2 text-heading-16 text-foreground">{title}</h2>
      {description && <p className="mx-auto max-w-md text-copy-14 text-gray-900">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </Card>
  )
}
