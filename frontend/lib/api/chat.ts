import type { RequestCore } from './request'
import type { ChatMessage, ChatMessageCreate } from './types'

export async function getChatHistory(core: RequestCore, params?: { skip?: number; limit?: number }): Promise<ChatMessage[]> {
  const search = new URLSearchParams()
  if (params?.skip !== undefined) search.set('skip', String(params.skip))
  if (params?.limit !== undefined) search.set('limit', String(params.limit))
  const query = search.toString()
  return core.request<ChatMessage[]>(`/api/chat${query ? `?${query}` : ''}`)
}

export async function sendChatMessage(core: RequestCore, data: ChatMessageCreate): Promise<ChatMessage> {
  return core.request<ChatMessage>('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function clearChatHistory(core: RequestCore): Promise<void> {
  return core.request<void>('/api/chat', { method: 'DELETE' })
}
