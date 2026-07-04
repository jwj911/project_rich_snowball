import { AlertTriangle } from 'lucide-react'
import Button from './Button'
import Card from './Card'

interface ErrorStateProps {
  title?: string
  message: string
  onRetry?: () => void
  className?: string
}

export default function ErrorState({
  title = '数据加载失败',
  message,
  onRetry,
  className = '',
}: ErrorStateProps) {
  return (
    <Card padding="lg" className={`border-red-900/40 bg-red-100/10 text-center ${className}`}>
      <AlertTriangle size={34} className="mx-auto mb-3 text-red-700" />
      <h2 className="mb-2 text-heading-16 text-foreground">{title}</h2>
      <p className="mx-auto max-w-md text-copy-14 text-red-900">{message}</p>
      {onRetry && (
        <Button type="button" onClick={onRetry} className="mt-4">
          重试
        </Button>
      )}
    </Card>
  )
}
