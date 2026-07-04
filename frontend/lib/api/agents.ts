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

export async function agentChatStream(
  core: RequestCore,
  data: AgentChatRequest,
  onEvent: (event: Record<string, unknown>) => void,
): Promise<void> {
  const resp = await fetch(`${API_BASE}/api/agents/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${core.getAccessToken() ?? ''}`,
    },
    body: JSON.stringify(data),
  })

  if (!resp.ok) {
    throw new Error(`Agent chat failed: ${resp.status}`)
  }

  const reader = resp.body?.getReader()
  if (!reader) return

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() ?? ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed.startsWith('data: ')) {
        try {
          const eventData = JSON.parse(trimmed.slice(6))
          onEvent(eventData)
        } catch {
          // ignore malformed lines
        }
      }
    }
  }
}
