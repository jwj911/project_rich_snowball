import { onCLS, onFCP, onFID, onLCP, onTTFB } from 'web-vitals'

function sendToAnalytics(metric: { name: string; value: number; id: string }) {
  console.log('[Web Vitals]', metric.name, metric.value, metric.id)
  // 生产环境替换为实际上报端点
}

export function reportWebVitals() {
  onCLS(sendToAnalytics)
  onFID(sendToAnalytics)
  onFCP(sendToAnalytics)
  onLCP(sendToAnalytics)
  onTTFB(sendToAnalytics)
}
