import type { ApiTransport } from './transport'
import { parseHeaderNumber } from './transport'
import type { FutContract, KlineData, RealtimeQuote, Variety, VarietyFees } from './types'

export function getRealtime(
  transport: ApiTransport,
  symbol: string,
  options: RequestInit = {},
): Promise<RealtimeQuote> {
  return transport.request<RealtimeQuote>(`/api/realtime/${encodeURIComponent(symbol)}`, options)
}

export function getRealtimeBatch(
  transport: ApiTransport,
  symbols: string[],
): Promise<{ quotes: RealtimeQuote[]; not_found: string[] }> {
  if (symbols.length === 0) return Promise.resolve({ quotes: [], not_found: [] })
  const params = new URLSearchParams()
  for (const symbol of symbols) params.append('symbols', symbol)
  return transport.request<{ quotes: RealtimeQuote[]; not_found: string[] }>(
    `/api/realtime/batch?${params.toString()}`,
  )
}

/** @deprecated SSE 鉴权已统一走 cookie-only 路径，stream-token 不再使用。 */
export function createRealtimeStreamToken(
  transport: ApiTransport,
  options: RequestInit = {},
): Promise<{ stream_token: string; expires_in: number }> {
  return transport.request<{ stream_token: string; expires_in: number }>('/api/realtime/stream-token', {
    method: 'POST',
    ...options,
  })
}

export function getKline(
  transport: ApiTransport,
  symbol: string,
  period: string = '1h',
  limit: number = 100,
  options: RequestInit = {},
): Promise<KlineData[]> {
  const searchParams = new URLSearchParams({
    period,
    limit: String(limit),
  })
  return transport.request<KlineData[]>(`/api/klines/${encodeURIComponent(symbol)}?${searchParams.toString()}`, options)
}

export function getContinuousKline(
  transport: ApiTransport,
  symbol: string,
  period: string = 'D',
  start?: string,
  end?: string,
  limit: number = 500,
  options: RequestInit = {},
): Promise<KlineData[]> {
  const params = new URLSearchParams()
  params.append('period', period)
  params.append('limit', String(limit))
  if (start) params.append('start', start)
  if (end) params.append('end', end)
  return transport.request<KlineData[]>(`/api/klines/${symbol}/continuous?${params.toString()}`, options)
}

export function getMainContractKline(
  transport: ApiTransport,
  symbol: string,
  period: string = 'D',
  start?: string,
  end?: string,
  limit: number = 500,
  options: RequestInit = {},
): Promise<KlineData[]> {
  const params = new URLSearchParams()
  params.append('period', period)
  params.append('limit', String(limit))
  if (start) params.append('start', start)
  if (end) params.append('end', end)
  return transport.request<KlineData[]>(`/api/klines/${symbol}/main?${params.toString()}`, options)
}

export function getContracts(
  transport: ApiTransport,
  varietyId: number,
  params?: { activeOnly?: boolean; skip?: number; limit?: number },
  options: RequestInit = {},
): Promise<FutContract[]> {
  const searchParams = new URLSearchParams()
  searchParams.append('variety_id', String(varietyId))
  if (params?.activeOnly !== undefined) searchParams.append('active_only', String(params.activeOnly))
  if (params?.skip !== undefined) searchParams.append('skip', String(params.skip))
  if (params?.limit !== undefined) searchParams.append('limit', String(params.limit))
  return transport.request<FutContract[]>(`/api/contracts?${searchParams.toString()}`, options)
}

export function getContractKline(
  transport: ApiTransport,
  contractId: number,
  period: string = 'D',
  start?: string,
  end?: string,
  limit: number = 500,
  options: RequestInit = {},
): Promise<KlineData[]> {
  const params = new URLSearchParams()
  params.append('period', period)
  params.append('limit', String(limit))
  if (start) params.append('start', start)
  if (end) params.append('end', end)
  return transport.request<KlineData[]>(`/api/contracts/${contractId}/kline?${params.toString()}`, options)
}

export function getVariety(transport: ApiTransport, symbol: string, options: RequestInit = {}): Promise<Variety> {
  return transport.request<Variety>(`/api/varieties/${symbol}`, options)
}

export async function getVarieties(
  transport: ApiTransport,
  params?: { category?: string; search?: string; skip?: number; limit?: number },
  options?: RequestInit,
): Promise<{ items: Variety[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params?.category) searchParams.append('category', params.category)
  if (params?.search) searchParams.append('search', params.search)
  if (params?.skip !== undefined) searchParams.append('skip', String(params.skip))
  if (params?.limit !== undefined) searchParams.append('limit', String(params.limit))
  const qs = searchParams.toString()
  const response = await transport.requestRaw(`/api/varieties${qs ? '?' + qs : ''}`, options)
  const items: Variety[] = await response.json()
  return { items, total: parseHeaderNumber(response.headers, 'X-Total-Count') }
}

export function getVarietyFees(transport: ApiTransport, symbol: string): Promise<VarietyFees> {
  return transport.request<VarietyFees>(`/api/varieties/${encodeURIComponent(symbol)}/fees`)
}

export function getMarketStatus(transport: ApiTransport): Promise<import('./types').MarketStatusResponse> {
  return transport.request('/api/market/status')
}
