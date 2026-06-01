import { sendFrontendLog } from './api/logging'

/**
 * 轻量级 Sentry 兼容层
 * 支持 console 占位输出、Sentry 真实 POST 上报、后端 /api/log/frontend fallback 三种模式。
 * 无论 Sentry 是否启用，异常和消息都会 fallback 到后端日志端点。
 */

export interface SentryConfig {
  dsn?: string
  enabled?: boolean
  reportUri?: string
  sampleRate?: number
  release?: string
  environment?: string
}

let config: SentryConfig = {
  enabled: process.env.NEXT_PUBLIC_SENTRY_ENABLED === 'true',
  reportUri: process.env.NEXT_PUBLIC_SENTRY_REPORT_URI || undefined,
  sampleRate: parseSampleRate(process.env.NEXT_PUBLIC_SENTRY_SAMPLE_RATE),
  release: process.env.NEXT_PUBLIC_RELEASE,
  environment: process.env.NODE_ENV,
}

function parseSampleRate(value: string | undefined): number {
  if (value === undefined || value === '') return 1
  const num = Number(value)
  if (Number.isNaN(num)) return 1
  return Math.max(0, Math.min(1, num))
}

function shouldReport(): boolean {
  if (!config.enabled) return false
  if (typeof window === 'undefined') return false
  const rate = config.sampleRate ?? 1
  if (rate <= 0) return false
  if (rate >= 1) return true
  return Math.random() < rate
}

async function sendToEndpoint(
  type: 'exception' | 'message',
  payload: unknown,
  level?: string,
) {
  if (!config.reportUri) return
  try {
    await fetch(config.reportUri, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type,
        payload,
        level,
        meta: {
          url: window.location.href,
          ua: navigator.userAgent,
          release: config.release,
          environment: config.environment,
          timestamp: new Date().toISOString(),
        },
      }),
      // 使用 keepalive 确保页面卸载时也能发送
      keepalive: true,
    })
  } catch {
    // 上报失败不抛错，避免死循环
  }
}

export function initSentry(c: SentryConfig) {
  config = {
    ...config,
    ...c,
    sampleRate: c.sampleRate ?? config.sampleRate,
  }
}

export function captureException(error: unknown, context?: Record<string, unknown>) {
  const payload = {
    error: error instanceof Error
      ? { name: error.name, message: error.message, stack: error.stack }
      : String(error),
    context,
  }
  // 无论 Sentry 是否启用，都向后端日志端点上报
  void sendFrontendLog({ type: 'error', payload, level: 'error' })

  if (!config.enabled) {
    console.error('[Sentry]', error, context)
    return
  }
  if (!shouldReport()) return
  void sendToEndpoint('exception', payload)
}

export function captureMessage(message: string, level: 'info' | 'warning' | 'error' = 'info') {
  // 无论 Sentry 是否启用，都向后端日志端点上报
  void sendFrontendLog({ type: 'log', payload: { message, level }, level })

  if (!config.enabled) {
    console.log(`[Sentry ${level}]`, message)
    return
  }
  if (!shouldReport()) return
  void sendToEndpoint('message', { message, level }, level)
}
