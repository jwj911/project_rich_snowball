import type { RequestCore } from './request'
import type { UserPreference, UserPreferenceUpdate } from './types'

export async function getUserSettings(core: RequestCore): Promise<UserPreference> {
  return core.request<UserPreference>('/api/settings')
}

export async function updateUserSettings(
  core: RequestCore,
  data: UserPreferenceUpdate,
): Promise<UserPreference> {
  return core.request<UserPreference>('/api/settings', {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}
