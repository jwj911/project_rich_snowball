import type { RequestCore } from './request'
import type { LLMConfigResponse, LLMConfigTestResponse, LLMConfigUpdate } from './types'

export async function getLLMConfig(core: RequestCore): Promise<LLMConfigResponse> {
  return core.request<LLMConfigResponse>('/api/llm-config')
}

export async function updateLLMConfig(
  core: RequestCore,
  data: LLMConfigUpdate,
): Promise<LLMConfigResponse> {
  return core.request<LLMConfigResponse>('/api/llm-config', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export async function testLLMConfig(
  core: RequestCore,
  data?: LLMConfigUpdate,
): Promise<LLMConfigTestResponse> {
  return core.request<LLMConfigTestResponse>('/api/llm-config/test', {
    method: 'POST',
    body: JSON.stringify(data ?? null),
  })
}

export async function deleteLLMApiKey(core: RequestCore): Promise<void> {
  await core.requestRaw('/api/llm-config/api-key', { method: 'DELETE' })
}
