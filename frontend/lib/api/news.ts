import type { RequestCore } from './request'
import type { NewsArticle, NewsSource } from './types'

export async function getNewsSources(core: RequestCore): Promise<NewsSource[]> {
  return core.request<NewsSource[]>('/api/news/sources')
}

export async function createNewsSource(
  core: RequestCore,
  data: { name: string; url: string; category?: string | null },
): Promise<NewsSource> {
  return core.request<NewsSource>('/api/news/sources', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deleteNewsSource(core: RequestCore, id: number): Promise<void> {
  return core.request<void>(`/api/news/sources/${id}`, { method: 'DELETE' })
}

export async function getNewsArticles(
  core: RequestCore,
  params?: {
    source_id?: number
    q?: string
    skip?: number
    limit?: number
  },
): Promise<NewsArticle[]> {
  const search = new URLSearchParams()
  if (params?.source_id !== undefined) search.set('source_id', String(params.source_id))
  if (params?.q) search.set('q', params.q)
  if (params?.skip !== undefined) search.set('skip', String(params.skip))
  if (params?.limit !== undefined) search.set('limit', String(params.limit))
  const query = search.toString()
  return core.request<NewsArticle[]>(`/api/news/articles${query ? `?${query}` : ''}`)
}

export async function summarizeArticle(core: RequestCore, id: number): Promise<NewsArticle> {
  return core.request<NewsArticle>(`/api/news/articles/${id}/summarize`, { method: 'POST' })
}
