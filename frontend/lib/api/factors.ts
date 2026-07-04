import type { RequestCore } from './request'
import type {
  FactorCreate,
  FactorDeleteResponse,
  FactorListParams,
  FactorResponse,
  FactorUpdate,
} from './types'

/**
 * 获取因子列表。
 *
 * 支持分页、模糊搜索、分类过滤和来源过滤。默认按 q_score 降序排列，
 * 将高质量因子排在前面。
 *
 * @param core - RequestCore 实例，提供底层请求能力
 * @param params - 查询参数，包含 skip/limit/q/category/source/is_builtin 等
 * @returns Promise 解析为因子列表（FactorResponse 数组）
 */
export async function listFactors(
  core: RequestCore,
  params: FactorListParams = {},
): Promise<FactorResponse[]> {
  const searchParams = new URLSearchParams()
  if (params.skip !== undefined) searchParams.append('skip', String(params.skip))
  if (params.limit !== undefined) searchParams.append('limit', String(params.limit))
  if (params.q) searchParams.append('q', params.q)
  if (params.category) searchParams.append('category', params.category)
  if (params.source) searchParams.append('source', params.source)
  if (params.is_builtin !== undefined) searchParams.append('is_builtin', String(params.is_builtin))

  const qs = searchParams.toString()
  return core.request<FactorResponse[]>(`/api/factors${qs ? '?' + qs : ''}`)
}

/**
 * 获取因子列表（带总数）。
 *
 * 与 listFactors 功能相同，但额外返回 X-Total-Count 响应头中的总记录数。
 *
 * @param core - RequestCore 实例
 * @param params - 查询参数
 * @returns Promise 解析为 { items: FactorResponse[], total: number }
 */
export async function listFactorsWithTotal(
  core: RequestCore,
  params: FactorListParams = {},
): Promise<{ items: FactorResponse[]; total: number }> {
  const searchParams = new URLSearchParams()
  if (params.skip !== undefined) searchParams.append('skip', String(params.skip))
  if (params.limit !== undefined) searchParams.append('limit', String(params.limit))
  if (params.q) searchParams.append('q', params.q)
  if (params.category) searchParams.append('category', params.category)
  if (params.source) searchParams.append('source', params.source)
  if (params.is_builtin !== undefined) searchParams.append('is_builtin', String(params.is_builtin))

  const qs = searchParams.toString()
  const response = await core.requestRaw(`/api/factors${qs ? '?' + qs : ''}`)
  const items: FactorResponse[] = await response.json()

  // 从响应头解析总记录数
  const totalHeader = response.headers.get('X-Total-Count')
  const total = totalHeader ? Number.parseInt(totalHeader, 10) : 0

  return { items, total: Number.isFinite(total) ? total : 0 }
}

/**
 * 根据 ID 获取单个因子详情。
 *
 * @param core - RequestCore 实例
 * @param id - 因子数据库主键 ID
 * @returns Promise 解析为因子详情
 */
export async function getFactor(core: RequestCore, id: number): Promise<FactorResponse> {
  return core.request<FactorResponse>(`/api/factors/${id}`)
}

/**
 * 创建自定义因子。
 *
 * 后端会自动设置 user_id、is_builtin=false、package_id 和 conversion_status。
 * 创建前会对 source_expression 进行公式合法性校验，校验失败会返回 400。
 *
 * @param core - RequestCore 实例
 * @param data - 创建因子请求数据
 * @returns Promise 解析为创建后的因子
 */
export async function createFactor(core: RequestCore, data: FactorCreate): Promise<FactorResponse> {
  return core.request<FactorResponse>('/api/factors', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

/**
 * 更新自定义因子（Patch 语义）。
 *
 * 仅支持更新用户自己创建的因子；系统内置因子（is_builtin=true）不可修改。
 * 如果修改了 source_expression，后端会重新进行公式合法性校验。
 *
 * @param core - RequestCore 实例
 * @param id - 因子数据库主键 ID
 * @param data - 更新字段，未设置的字段保持原值不变
 * @returns Promise 解析为更新后的因子
 */
export async function updateFactor(
  core: RequestCore,
  id: number,
  data: FactorUpdate,
): Promise<FactorResponse> {
  return core.request<FactorResponse>(`/api/factors/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

/**
 * 软删除自定义因子。
 *
 * 仅支持删除用户自己创建的因子；系统内置因子不可删除。
 * 后端实际执行 is_active = False 的软删除操作。
 *
 * @param core - RequestCore 实例
 * @param id - 因子数据库主键 ID
 * @returns Promise 解析为删除结果消息
 */
export async function deleteFactor(
  core: RequestCore,
  id: number,
): Promise<FactorDeleteResponse> {
  return core.request<FactorDeleteResponse>(`/api/factors/${id}`, {
    method: 'DELETE',
  })
}
