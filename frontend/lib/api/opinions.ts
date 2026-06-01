import type { RequestCore } from './request'
import type { Opinion, OpinionCreate, OpinionUpdate } from './types'

export async function getOpinions(
  core: RequestCore,
  params?: {
    variety_id?: number
    status?: string
    skip?: number
    limit?: number
  },
): Promise<Opinion[]> {
  const search = new URLSearchParams()
  if (params?.variety_id !== undefined) search.set('variety_id', String(params.variety_id))
  if (params?.status) search.set('status', params.status)
  if (params?.skip !== undefined) search.set('skip', String(params.skip))
  if (params?.limit !== undefined) search.set('limit', String(params.limit))
  const query = search.toString()
  return core.request<Opinion[]>(`/api/opinions${query ? `?${query}` : ''}`)
}

export async function getMyOpinions(
  core: RequestCore,
  params?: {
    status?: string
    skip?: number
    limit?: number
  },
): Promise<Opinion[]> {
  const search = new URLSearchParams()
  if (params?.status) search.set('status', params.status)
  if (params?.skip !== undefined) search.set('skip', String(params.skip))
  if (params?.limit !== undefined) search.set('limit', String(params.limit))
  const query = search.toString()
  return core.request<Opinion[]>(`/api/opinions/me${query ? `?${query}` : ''}`)
}

export async function getOpinionById(core: RequestCore, id: number): Promise<Opinion> {
  return core.request<Opinion>(`/api/opinions/${id}`)
}

export async function createOpinion(core: RequestCore, data: OpinionCreate): Promise<Opinion> {
  return core.request<Opinion>('/api/opinions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function updateOpinion(
  core: RequestCore,
  id: number,
  data: OpinionUpdate,
): Promise<Opinion> {
  return core.request<Opinion>(`/api/opinions/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deleteOpinion(core: RequestCore, id: number): Promise<void> {
  return core.request<void>(`/api/opinions/${id}`, { method: 'DELETE' })
}
