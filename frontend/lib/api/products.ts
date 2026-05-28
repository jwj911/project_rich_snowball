import type { ApiTransport } from './transport'
import { parseHeaderNumber } from './transport'
import type { Comment, Product, ProductDetail, ProductListResponse, ProductQuery } from './types'

/** 将 VarietyWithQuoteResponse 映射为前端 Product 接口（字段兼容层）。 */
function _mapVarietyToProduct(v: Record<string, unknown>): Product {
  return {
    id: v.id as number,
    name: v.name as string,
    symbol: v.symbol as string,
    current_price: (v.current_price as number | null) ?? null,
    change_percent: (v.change_percent as number | null | undefined) ?? null,
    open_price: (v.open_price as number | null) ?? null,
    high: (v.high as number | null) ?? null,
    low: (v.low as number | null) ?? null,
    volume: (v.volume as number | null) ?? null,
    category: (v.category as string | null) ?? null,
    margin: (v.margin_rate as number | null) ?? (v.margin as number | null) ?? null,
    commission: (v.commission as number | null) ?? null,
    updated_at: (v.updated_at as string) ?? '',
    limit_up: (v.limit_up as number | null) ?? null,
    limit_down: (v.limit_down as number | null) ?? null,
    price_precision: (v.price_precision as number) ?? 2,
    margin_rate: v.margin_rate as number | null | undefined,
    contract_code: v.contract_code as string | undefined,
    exchange: v.exchange as string | undefined,
    tick_size: v.tick_size as number | null | undefined,
  }
}

export async function getProducts(transport: ApiTransport, options: RequestInit = {}): Promise<Product[]> {
  const response = await getProductsPage(transport, {}, options)
  return response.items
}

export async function getProductsPage(
  transport: ApiTransport,
  params: ProductQuery = {},
  options: RequestInit = {},
): Promise<ProductListResponse> {
  const searchParams = new URLSearchParams()
  if (params.skip !== undefined) searchParams.append('skip', String(params.skip))
  if (params.limit !== undefined) searchParams.append('limit', String(params.limit))
  if (params.search) searchParams.append('search', params.search)
  if (params.category && params.category !== 'all') searchParams.append('category', params.category)
  if (params.direction && params.direction !== 'all') searchParams.append('direction', params.direction)
  if (params.sortBy) searchParams.append('sort_by', params.sortBy)
  if (params.sortOrder) searchParams.append('sort_order', params.sortOrder)

  const qs = searchParams.toString()
  // 已迁移到 /api/varieties（ProductDB 退场 Phase 2）
  const response = await transport.requestRaw(`/api/varieties${qs ? '?' + qs : ''}`, options)
  const rawItems: Record<string, unknown>[] = await response.json()
  const items = rawItems.map(_mapVarietyToProduct)

  const categories = (response.headers.get('X-Categories') || '')
    .split(',')
    .map((category) => category.trim())
    .filter(Boolean)
    .map((category) => {
      try {
        return decodeURIComponent(category)
      } catch {
        return category
      }
    })

  return {
    items,
    total: parseHeaderNumber(response.headers, 'X-Total-Count'),
    totalVolume: parseHeaderNumber(response.headers, 'X-Total-Volume'),
    upCount: parseHeaderNumber(response.headers, 'X-Up-Count'),
    downCount: parseHeaderNumber(response.headers, 'X-Down-Count'),
    categories,
  }
}

export async function getProductBySymbol(transport: ApiTransport, symbol: string, options: RequestInit = {}): Promise<ProductDetail> {
  const variety = await transport.request<Record<string, unknown>>(`/api/varieties/${encodeURIComponent(symbol)}/detail`, options)
  const comments = (variety.comments as Comment[] | undefined) ?? []
  return {
    product: _mapVarietyToProduct(variety),
    comments,
  }
}

export function createComment(
  transport: ApiTransport,
  content: string,
  priceLevelId?: number,
  varietyId?: number,
): Promise<Comment> {
  return transport.request<Comment>('/api/comments', {
    method: 'POST',
    body: JSON.stringify({ content, price_level_id: priceLevelId, variety_id: varietyId }),
  })
}

export function getUserComments(transport: ApiTransport, username: string): Promise<Comment[]> {
  return transport.request<Comment[]>(`/api/comments/user/${encodeURIComponent(username)}`)
}
