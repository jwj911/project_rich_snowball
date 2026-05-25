import { onCLS, onFCP, onINP, onLCP, onTTFB } from 'web-vitals'

/**
 * TODO: 当前为开发占位实现，仅输出到 console。
 *       生产环境需替换为实际上报端点（如 /api/log/vitals 或 Analytics 服务）。
 */
function sendToAnalytics(metric: { name: string; value: number; id: string }) {
  console.log('[Web Vitals]', metric.name, metric.value, metric.id)
}

export function reportWebVitals() {
  onCLS(sendToAnalytics)
  onINP(sendToAnalytics)
  onFCP(sendToAnalytics)
  onLCP(sendToAnalytics)
  onTTFB(sendToAnalytics)
}
