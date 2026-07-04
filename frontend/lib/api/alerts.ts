import type { RequestCore } from './request'
import type { AlertEvent, AlertEventQuery, AlertSummary } from './types'

export async function getAlertEvents(core: RequestCore, params?: AlertEventQuery): Promise<AlertEvent[]> {
  const search = new URLSearchParams()
  if (params?.category) search.set('category', params.category)
  if (params?.severity) search.set('severity', params.severity)
  if (params?.unread_only !== undefined) search.set('unread_only', String(params.unread_only))
  if (params?.skip !== undefined) search.set('skip', String(params.skip))
  if (params?.limit !== undefined) search.set('limit', String(params.limit))
  const query = search.toString()
  return core.request<AlertEvent[]>(`/api/alerts/events${query ? `?${query}` : ''}`)
}

export async function getAlertSummary(core: RequestCore): Promise<AlertSummary> {
  return core.request<AlertSummary>('/api/alerts/summary')
}

export async function markAlertEventRead(core: RequestCore, id: number): Promise<AlertEvent> {
  return core.request<AlertEvent>(`/api/alerts/events/${id}/read`, { method: 'PUT' })
}

export async function dismissAlertEvent(core: RequestCore, id: number): Promise<AlertEvent> {
  return core.request<AlertEvent>(`/api/alerts/events/${id}/dismiss`, { method: 'PUT' })
}
