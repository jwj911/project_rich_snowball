/**
 * 轻量级 Sentry 兼容层
 * TODO: 当前为开发占位实现，仅输出到 console。
 *       生产环境需替换为 @sentry/nextjs 完整集成或接入真实上报端点。
 */
interface SentryConfig {
  dsn?: string
  enabled?: boolean
  reportUri?: string
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
  // TODO: 生产环境发送给真实 Sentry 端点
}

export function captureMessage(message: string, level: 'info' | 'warning' | 'error' = 'info') {
  if (!config.enabled) {
    console.log(`[Sentry ${level}]`, message)
    return
  }
  // TODO: 生产环境发送给真实 Sentry 端点
}
