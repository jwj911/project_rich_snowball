import { API_BASE } from './request'
import type { RequestCore } from './request'
import type { AgentTaskResponse, AgentChatRequest, AgentPermissionHeartbeat, AgentStatusSummary } from './types'

export async function getAgentTasks(
  core: RequestCore,
  params?: { status?: string; skip?: number; limit?: number },
): Promise<AgentTaskResponse[]> {
  const search = new URLSearchParams()
  if (params?.status) search.set('status', params.status)
  if (params?.skip !== undefined) search.set('skip', String(params.skip))
  if (params?.limit !== undefined) search.set('limit', String(params.limit))
  const query = search.toString()
  return core.request<AgentTaskResponse[]>(`/api/agents/tasks${query ? `?${query}` : ''}`)
}

export async function getAgentTask(core: RequestCore, taskId: number): Promise<AgentTaskResponse> {
  return core.request<AgentTaskResponse>(`/api/agents/tasks/${taskId}`)
}

export async function getAgentStatus(core: RequestCore): Promise<AgentStatusSummary> {
  return core.request<AgentStatusSummary>('/api/agents/status')
}

export async function getAgentPermissionHeartbeat(core: RequestCore): Promise<AgentPermissionHeartbeat> {
  return core.request<AgentPermissionHeartbeat>('/api/agents/permission-heartbeat')
}

export async function createAgentTask(
  core: RequestCore,
  data: { agent_type: string; query: string },
): Promise<AgentTaskResponse> {
  return core.request<AgentTaskResponse>('/api/agents/tasks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deleteAgentTask(core: RequestCore, taskId: number): Promise<void> {
  return core.request<void>(`/api/agents/tasks/${taskId}`, { method: 'DELETE' })
}

export interface AgentChatStreamOptions {
  signal?: AbortSignal
  onMalformed?: (raw: string) => void
}

export async function agentChatStream(
  core: RequestCore,
  data: AgentChatRequest,
  onEvent: (event: Record<string, unknown>) => void,
  options: AgentChatStreamOptions = {},
): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/agents/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${core.getAccessToken() ?? ''}`,
    },
    body: JSON.stringify(data),
    signal: options.signal,
  })

  if (!resp.ok) {
    let detail = `Agent chat failed: ${resp.status}`
    try {
      const body = await resp.json()
      if (body?.detail) detail = body.detail
      else if (body?.message) detail = body.message
    } catch {
      // ignore
    }
    throw new Error(detail)
  }

  const reader = resp.body?.getReader()
  if (!reader) return

  const decoder = new TextDecoder()
  let buffer = ''
  let pendingEventType = 'message'

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      // 保留最后一个不完整的行
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed) {
          // SSE 空行表示事件结束，重置事件类型
          pendingEventType = 'message'
          continue
        }
        if (trimmed.startsWith('event: ')) {
          pendingEventType = trimmed.slice(7).trim()
          continue
        }
        if (trimmed.startsWith('data: ')) {
          try {
            const eventData = JSON.parse(trimmed.slice(6))
            onEvent(eventData)
          } catch {
            if (options.onMalformed) {
              options.onMalformed(trimmed)
            }
            // eslint-disable-next-line no-console
            console.warn('Malformed SSE data line:', trimmed)
          }
          continue
        }
        // 其他行（如 id: / retry:）忽略
      }
    }
  } catch (e) {
    // AbortError 是正常取消，不抛错
    if (e instanceof Error && e.name === 'AbortError') {
      return
    }
    throw e
  } finally {
    try {
      reader.cancel()
    } catch {
      // ignore
    }
  }
}
