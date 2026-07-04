import { API_BASE } from './request'
import type { RequestCore } from './request'
import type { StrategyResponse, StrategyCreate, BacktestRunResponse, StrategyBacktestRequest } from './types'

export async function getStrategies(core: RequestCore): Promise<StrategyResponse[]> {
  return core.request<StrategyResponse[]>('/api/strategies')
}

export async function createStrategy(core: RequestCore, data: StrategyCreate): Promise<StrategyResponse> {
  return core.request<StrategyResponse>('/api/strategies', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function deleteStrategy(core: RequestCore, strategyId: number): Promise<{ message: string }> {
  return core.request<{ message: string }>(`/api/strategies/${strategyId}`, { method: 'DELETE' })
}

export async function runStrategyBacktest(
  core: RequestCore,
  strategyId: number,
  data: StrategyBacktestRequest,
): Promise<BacktestRunResponse> {
  return core.request<BacktestRunResponse>(`/api/strategies/${strategyId}/backtest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export async function getStrategyBacktests(core: RequestCore, strategyId: number): Promise<BacktestRunResponse[]> {
  return core.request<BacktestRunResponse[]>(`/api/strategies/${strategyId}/backtests`)
}
