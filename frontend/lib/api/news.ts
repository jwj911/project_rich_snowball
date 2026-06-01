import type { RequestCore } from './request'
import type { NewsArticle, NewsSource } from './types'

export async function getNewsSources(core: RequestCore): Promise<NewsSource[]> {
  return core.request<NewsSource[]>('/api/news/sources')
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
