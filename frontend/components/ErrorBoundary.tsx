'use client'

import { Component, ErrorInfo, ReactNode } from 'react'
import { captureException } from '@/lib/sentry-lite'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error?: Error
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('ErrorBoundary caught:', error, errorInfo)
    captureException(error, { componentStack: errorInfo.componentStack })
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? (
        <div className="flex min-h-[400px] flex-col items-center justify-center rounded-lg border border-red-900/50 bg-red-950/20 p-8 text-center">
          <h2 className="text-lg font-semibold text-red-300">页面出现错误</h2>
          <p className="mt-2 text-sm text-slate-400">
            {this.state.error?.message ?? '未知错误'}
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="mt-4 rounded-lg bg-red-600 px-4 py-2 text-sm text-white hover:bg-red-700"
          >
            刷新页面
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
