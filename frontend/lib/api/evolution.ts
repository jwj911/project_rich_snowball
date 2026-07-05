import type { RequestCore } from './request'
import type {
  EvolutionRunListResponse,
  EvolutionRunDetailResponse,
  StrategyLifecycleResponse,
  DecayEvaluationRequest,
  DecayEvaluationResponse,
  LifecycleComparisonRequest,
  LifecycleComparisonResponse,
} from './types'

/**
 * 获取进化运行记录列表。
 */
export async function getEvolutionRuns(
  core: RequestCore,
  params?: { symbol?: string; status?: string; skip?: number; limit?: number },
): Promise<EvolutionRunListResponse> {
  const searchParams = new URLSearchParams()
  if (params?.symbol) searchParams.set('symbol', params.symbol)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.skip !== undefined) searchParams.set('skip', String(params.skip))
  if (params?.limit !== undefined) searchParams.set('limit', String(params.limit))

  const qs = searchParams.toString()
  return core.request<EvolutionRunListResponse>(`/api/evolution/runs${qs ? `?${qs}` : ''}`)
}

/**
 * 获取单次进化运行详情（含代际快照）。
 */
export async function getEvolutionRun(
  core: RequestCore,
  runId: number,
): Promise<EvolutionRunDetailResponse> {
  return core.request<EvolutionRunDetailResponse>(`/api/evolution/runs/${runId}`)
}

/**
 * 获取单个策略的生命周期详情。
 */
export async function getStrategyLifecycle(
  core: RequestCore,
  strategyId: number,
): Promise<StrategyLifecycleResponse> {
  return core.request<StrategyLifecycleResponse>(`/api/evolution/lifecycle/${strategyId}`)
}

/**
 * 获取当前用户所有策略的生命周期记录。
 */
export async function listLifecycles(
  core: RequestCore,
  status?: string,
): Promise<StrategyLifecycleResponse[]> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : ''
  return core.request<StrategyLifecycleResponse[]>(`/api/evolution/lifecycles${qs}`)
}

/**
 * 评估策略退化程度。
 */
export async function evaluateDecay(
  core: RequestCore,
  data: DecayEvaluationRequest,
): Promise<DecayEvaluationResponse> {
  return core.request<DecayEvaluationResponse>('/api/evolution/evaluate-decay', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

/**
 * 对比多个策略的生命周期状态。
 */
export async function compareLifecycles(
  core: RequestCore,
  data: LifecycleComparisonRequest,
): Promise<LifecycleComparisonResponse> {
  return core.request<LifecycleComparisonResponse>('/api/evolution/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}
