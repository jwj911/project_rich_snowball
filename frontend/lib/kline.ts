import { api, KlineData } from '@/lib/api'

export type KlinePeriod = '1m' | '5m' | '15m' | '30m' | '1h' | '1d' | '1w'
export type KlineSource = 'continuous' | 'main' | 'single'

export const KLINE_SOURCES: Array<{ value: KlineSource; label: string }> = [
  { value: 'continuous', label: '连续 K 线' },
  { value: 'main', label: '主力合约' },
  { value: 'single', label: '具体合约' },
]

export const KLINE_PERIODS: Array<{ value: KlinePeriod; label: string }> = [
  { value: '1m', label: '1 分' },
  { value: '5m', label: '5 分' },
  { value: '15m', label: '15 分' },
  { value: '30m', label: '30 分' },
  { value: '1h', label: '1 小时' },
  { value: '1d', label: '日线' },
  { value: '1w', label: '周线' },
]

export const KLINE_PERIOD_LIMITS: Record<KlinePeriod, number> = {
  '1m': 120,
  '5m': 120,
  '15m': 120,
  '30m': 120,
  '1h': 100,
  '1d': 90,
  '1w': 90,
}

const CONTRACT_PERIOD_MAP: Record<KlinePeriod, string> = {
  '1m': '1',
  '5m': '5',
  '15m': '15',
  '30m': '30',
  '1h': '60',
  '1d': 'D',
  '1w': 'W',
}

export interface KlineLoadResult {
  rows: KlineData[]
  period: KlinePeriod
  notice: string | null
}

export interface KlineLoadOptions {
  contractId?: number | null
  contractCode?: string | null
  signal?: AbortSignal
}

export async function loadKlineBySource(
  symbol: string,
  source: KlineSource,
  period: KlinePeriod,
  options: KlineLoadOptions = {},
): Promise<KlineLoadResult> {
  const limit = KLINE_PERIOD_LIMITS[period]
  try {
    let rows: KlineData[]
    switch (source) {
      case 'continuous':
        rows = await api.getContinuousKline(symbol, period, undefined, undefined, limit, { signal: options.signal })
        break
      case 'main':
        rows = await api.getMainContractKline(symbol, period, undefined, undefined, limit, { signal: options.signal })
        break
      case 'single':
        if (!options.contractId) {
          return {
            rows: [],
            period,
            notice: '请先选择一个具体合约。',
          }
        }
        rows = await api.getContractKline(
          options.contractId,
          CONTRACT_PERIOD_MAP[period],
          undefined,
          undefined,
          limit,
          { signal: options.signal },
        )
        rows = rows.map((row) => ({
          ...row,
          contract_code: row.contract_code ?? options.contractCode ?? null,
        }))
        break
      default:
        rows = await api.getKline(symbol, period, limit, { signal: options.signal })
        break
    }

    if (rows.length > 0) {
      return { rows, period, notice: null }
    }

    const sourceLabel = KLINE_SOURCES.find((s) => s.value === source)?.label ?? source
    const sourceHint = source === 'continuous'
      ? '，可尝试切换到主力合约或具体合约'
      : source === 'main'
        ? '，可尝试切换到具体合约'
        : ''
    return {
      rows,
      period,
      notice: `${sourceLabel}（${period}）暂无 K 线数据${sourceHint}`,
    }
  } catch (err) {
    if (options.signal?.aborted) {
      throw err
    }
    return {
      rows: [],
      period,
      notice: err instanceof Error ? err.message : 'K 线数据加载失败',
    }
  }
}
