import { API_BASE } from './request'

const LOG_ENDPOINT = `${API_BASE}/api/log/frontend`

export interface FrontendLogPayload {
  type: 'error' | 'log' | 'web-vitals'
  payload: unknown
  level?: 'debug' | 'info' | 'warning' | 'error'
  meta?: Record<string, unknown>
}

/**
 * 向后端 /api/log/frontend 上报日志。
 * 不要求认证（endpoint 本身不检查 token），失败静默丢弃。
 */
export async function sendFrontendLog(data: FrontendLogPayload): Promise<void> {
  try {
    await fetch(LOG_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...data,
        meta: {
          url: typeof window !== 'undefined' ? window.location.href : null,
          ua: typeof window !== 'undefined' ? navigator.userAgent : null,
          release: process.env.NEXT_PUBLIC_RELEASE,
          environment: process.env.NODE_ENV,
          timestamp: new Date().toISOString(),
          ...(data.meta || {}),
        },
      }),
      // keepalive 保证页面卸载时也能发送
      keepalive: true,
    })
  } catch {
    // 写入失败时降级为静默丢弃，不向前端抛错
  }
}
