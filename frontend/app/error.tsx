'use client'

import ErrorState from '@/components/ui/ErrorState'

export default function AppError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-10">
      <ErrorState
        title="页面暂时无法显示"
        message={error.message || '页面渲染时遇到异常，请稍后重试。'}
        onRetry={reset}
        className="w-full max-w-xl"
      />
    </main>
  )
}
