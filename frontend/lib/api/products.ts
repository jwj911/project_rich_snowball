import type { ApiTransport } from './transport'
import { parseHeaderNumber } from './transport'
import type { Comment, Product, ProductDetail, ProductListResponse, ProductQuery } from './types'

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
  const response = await transport.requestRaw(`/api/products${qs ? '?' + qs : ''}`, options)
  const items: Product[] = await response.json()
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

export function getProduct(transport: ApiTransport, id: number, options: RequestInit = {}): Promise<ProductDetail> {
  return transport.request<ProductDetail>(`/api/products/${id}`, options)
}

export function createComment(
  transport: ApiTransport,
  productId: number,
  content: string,
  priceLevelId?: number,
): Promise<Comment> {
  return transport.request<Comment>('/api/comments', {
    method: 'POST',
    body: JSON.stringify({ product_id: productId, content, price_level_id: priceLevelId }),
  })
}

export function getUserComments(transport: ApiTransport, username: string): Promise<Comment[]> {
  return transport.request<Comment[]>(`/api/comments/user/${encodeURIComponent(username)}`)
}
