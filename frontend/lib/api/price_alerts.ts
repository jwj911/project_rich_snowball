import type { RequestCore } from './request'
import type { PriceAlert, PriceAlertCreate, PriceAlertUpdate } from './types'

export async function getPriceAlerts(
  core: RequestCore,
  params?: {
    variety_id?: number
    triggered?: boolean
    skip?: number
    limit?: number
  },
): Promise<PriceAlert[]> {
  const search = new URLSearchParams()
  if (params?.variety_id !== undefined) search.set('variety_id', String(params.variety_id))
  if (params?.triggered !== undefined) search.set('triggered', String(params.triggered))
  if (params?.skip !== undefined) search.set('skip', String(params.skip))
  if (params?.limit !== undefined) search.set('limit', String(params.limit))
  const query = search.toString()
  return core.request<PriceAlert[]>(`/api/price-alerts${query ? `?${query}` : ''}`)
}

export async function getTriggeredAlerts(core: RequestCore, params?: { skip?: number; limit?: number }): Promise<PriceAlert[]> {
  const search = new URLSearchParams()
  if (params?.skip !== undefined) search.set('skip', String(params.skip))
  if (params?.limit !== undefined) search.set('limit', String(params.limit))
  const query = search.toString()
  return core.request<PriceAlert[]>(`/api/price-alerts/triggered${query ? `?${query}` : ''}`)
}

export async function createPriceAlert(core: RequestCore, data: PriceAlertCreate): Promise<PriceAlert> {
  return core.request<PriceAlert>('/api/price-alerts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function updatePriceAlert(core: RequestCore, id: number, data: PriceAlertUpdate): Promise<PriceAlert> {
  return core.request<PriceAlert>(`/api/price-alerts/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deletePriceAlert(core: RequestCore, id: number): Promise<void> {
  return core.request<void>(`/api/price-alerts/${id}`, { method: 'DELETE' })
}
