import type { Metadata } from 'next'
import './globals.css'
import { AuthProvider } from '@/components/auth/AuthProvider'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import WebVitalsReporter from '@/components/WebVitalsReporter'
import { Toaster } from 'sonner'

export const metadata: Metadata = {
  title: '倍增计划',
  description: '倍增计划期货行情与私密交流社区',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-CN">
      <body>
        <ErrorBoundary>
          <AuthProvider>
            {children}
            <Toaster position="top-right" theme="dark" />
            <WebVitalsReporter />
          </AuthProvider>
        </ErrorBoundary>
      </body>
    </html>
  )
}
