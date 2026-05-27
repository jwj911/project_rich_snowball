import { onCLS, onFCP, onINP, onLCP, onTTFB } from 'web-vitals'

export interface VitalsConfig {
  reportUri?: string
  sampleRate?: number
}

function parseSampleRate(value: string | undefined): number {
  if (value === undefined || value === '') return 1
  const num = Number(value)
  if (Number.isNaN(num)) return 1
  return Math.max(0, Math.min(1, num))
}

function getConfig(): VitalsConfig {
  return {
    reportUri: process.env.NEXT_PUBLIC_SENTRY_REPORT_URI || undefined,
    sampleRate: parseSampleRate(process.env.NEXT_PUBLIC_SENTRY_SAMPLE_RATE),
  }
}

function shouldReport(config: VitalsConfig): boolean {
  if (!config.reportUri) return false
  const rate = config.sampleRate ?? 1
  if (rate <= 0) return false
  if (rate >= 1) return true
  return Math.random() < rate
}

async function sendToEndpoint(config: VitalsConfig, metric: { name: string; value: number; id: string }) {
  if (!config.reportUri) return
  try {
    await fetch(config.reportUri, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'web-vitals',
        payload: {
          name: metric.name,
          value: metric.value,
          id: metric.id,
          route: typeof window !== 'undefined' ? window.location.pathname : null,
        },
        meta: {
          url: typeof window !== 'undefined' ? window.location.href : null,
          ua: typeof window !== 'undefined' ? navigator.userAgent : null,
          release: process.env.NEXT_PUBLIC_RELEASE,
          environment: process.env.NODE_ENV,
          timestamp: new Date().toISOString(),
        },
      }),
      keepalive: true,
    })
  } catch {
    // 上报失败不抛错
  }
}

function sendToAnalytics(metric: { name: string; value: number; id: string }) {
  console.log('[Web Vitals]', metric.name, metric.value, metric.id)

  const config = getConfig()
  if (shouldReport(config)) {
    void sendToEndpoint(config, metric)
  }
}

export function reportWebVitals() {
  onCLS(sendToAnalytics)
  onINP(sendToAnalytics)
  onFCP(sendToAnalytics)
  onLCP(sendToAnalytics)
  onTTFB(sendToAnalytics)
}
