/**
 * 轻量级 Sentry 兼容层
 * 生产环境替换为 @sentry/nextjs 完整集成
 */
interface SentryConfig {
  dsn?: string
  enabled?: boolean
}

let config: SentryConfig = { enabled: false }

export function initSentry(c: SentryConfig) {
  config = c
}

export function captureException(error: unknown, context?: Record<string, unknown>) {
  if (!config.enabled) {
    console.error('[Sentry]', error, context)
    return
  }
  // 生产环境发送给 Sentry
}

export function captureMessage(message: string, level: 'info' | 'warning' | 'error' = 'info') {
  if (!config.enabled) {
    console.log(`[Sentry ${level}]`, message)
    return
  }
}
