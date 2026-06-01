import type { RequestCore } from './request'
import type { TradeRecord, TradeRecordCreate, TradeRecordClose } from './types'

export async function getPortfolio(
  core: RequestCore,
  params?: {
    status?: string
    skip?: number
    limit?: number
  },
): Promise<TradeRecord[]> {
  const search = new URLSearchParams()
  if (params?.status) search.set('status', params.status)
  if (params?.skip !== undefined) search.set('skip', String(params.skip))
  if (params?.limit !== undefined) search.set('limit', String(params.limit))
  const query = search.toString()
  return core.request<TradeRecord[]>(`/api/portfolio${query ? `?${query}` : ''}`)
}

export async function createTradeRecord(core: RequestCore, data: TradeRecordCreate): Promise<TradeRecord> {
  return core.request<TradeRecord>('/api/portfolio', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function closeTradeRecord(core: RequestCore, id: number, data: TradeRecordClose): Promise<TradeRecord> {
  return core.request<TradeRecord>(`/api/portfolio/${id}/close`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deleteTradeRecord(core: RequestCore, id: number): Promise<void> {
  return core.request<void>(`/api/portfolio/${id}`, { method: 'DELETE' })
}
