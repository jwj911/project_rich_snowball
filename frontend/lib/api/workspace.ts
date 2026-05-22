import type { ApiTransport } from './transport'
import type { PriceLevel, Watchlist, WorkspaceSummary } from './types'

export function getPriceLevels(
  transport: ApiTransport,
  varietyId?: number,
  type?: 'support' | 'resistance',
): Promise<PriceLevel[]> {
  const searchParams = new URLSearchParams()
  if (varietyId !== undefined) searchParams.append('variety_id', String(varietyId))
  if (type) searchParams.append('type', type)
  const qs = searchParams.toString()
  return transport.request<PriceLevel[]>(`/api/price-levels${qs ? '?' + qs : ''}`)
}

export function createPriceLevel(
  transport: ApiTransport,
  varietyId: number,
  type: 'support' | 'resistance',
  price: string,
  note?: string,
): Promise<PriceLevel> {
  return transport.request<PriceLevel>('/api/price-levels', {
    method: 'POST',
    body: JSON.stringify({ variety_id: varietyId, type, price, note }),
  })
}

export function updatePriceLevel(
  transport: ApiTransport,
  id: number,
  updates: { price?: string; note?: string },
): Promise<PriceLevel> {
  return transport.request<PriceLevel>(`/api/price-levels/${id}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  })
}

export function deletePriceLevel(transport: ApiTransport, id: number): Promise<void> {
  return transport.request<void>(`/api/price-levels/${id}`, { method: 'DELETE' })
}

export function createPriceLevelsBatch(
  transport: ApiTransport,
  items: Array<{
    variety_id: number
    type: 'support' | 'resistance'
    price: string
    note?: string | null
  }>,
): Promise<{
  success: PriceLevel[]
  failed: Array<{ index: number; reason: string }>
  created_count: number
  failed_count: number
}> {
  return transport.request('/api/price-levels/batch', {
    method: 'POST',
    body: JSON.stringify({ items }),
  })
}

export function getWatchlists(transport: ApiTransport, varietyId?: number): Promise<Watchlist[]> {
  const searchParams = new URLSearchParams()
  if (varietyId !== undefined) searchParams.append('variety_id', String(varietyId))
  const qs = searchParams.toString()
  return transport.request<Watchlist[]>(`/api/watchlists${qs ? '?' + qs : ''}`)
}

export function createWatchlist(transport: ApiTransport, varietyId: number, notes?: string): Promise<Watchlist> {
  return transport.request<Watchlist>('/api/watchlists', {
    method: 'POST',
    body: JSON.stringify({ variety_id: varietyId, notes }),
  })
}

export function updateWatchlist(
  transport: ApiTransport,
  id: number,
  updates: { notes?: string; is_notified?: boolean },
): Promise<Watchlist> {
  return transport.request<Watchlist>(`/api/watchlists/${id}`, {
    method: 'PUT',
    body: JSON.stringify(updates),
  })
}

export function deleteWatchlist(transport: ApiTransport, id: number): Promise<void> {
  return transport.request<void>(`/api/watchlists/${id}`, { method: 'DELETE' })
}

export function getWorkspace(transport: ApiTransport, options: RequestInit = {}): Promise<WorkspaceSummary> {
  return transport.request<WorkspaceSummary>('/api/workspace/me', options)
}
