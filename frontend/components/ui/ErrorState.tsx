import { AlertTriangle } from 'lucide-react'
import Button from './Button'

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
    <div className={`rounded-lg border border-red-500/30 bg-red-500/10 p-6 text-center ${className}`}>
      <AlertTriangle size={34} className="mx-auto mb-3 text-red-400" />
      <h2 className="mb-2 text-lg font-semibold text-white">{title}</h2>
      <p className="mx-auto max-w-md text-sm leading-6 text-red-100/80">{message}</p>
      {onRetry && (
        <Button type="button" onClick={onRetry} className="mt-4">
          重试
        </Button>
      )}
    </div>
  )
}

