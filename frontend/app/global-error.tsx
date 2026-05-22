'use client'

import './globals.css'
import ErrorState from '@/components/ui/ErrorState'

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset: () => void
}) {
  return (
    <html lang="zh-CN">
      <body>
        <main className="flex min-h-screen items-center justify-center bg-slate-950 px-4 py-10">
          <ErrorState
            title="应用暂时无法启动"
            message={error.message || '应用加载时遇到异常，请刷新或稍后重试。'}
            onRetry={reset}
            className="w-full max-w-xl"
          />
        </main>
      </body>
    </html>
  )
}
