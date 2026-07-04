import { api, KlineData } from '@/lib/api'
import { KLINE } from '@/lib/constants'

export type KlinePeriod = '1d'
export type KlineSource = 'main'

export const KLINE_SOURCES: Array<{ value: KlineSource; label: string }> = [
  { value: 'main', label: '主力合约' },
]

export const KLINE_PERIODS: Array<{ value: KlinePeriod; label: string }> = [
  { value: '1d', label: '日线' },
]

export const KLINE_PERIOD_LIMITS: Record<KlinePeriod, number> = {
  '1d': KLINE.LONG_PERIOD_LIMIT,
}

const CONTRACT_PERIOD_MAP: Record<KlinePeriod, string> = {
  '1d': 'D',
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
  const defaultStart = '2025-01-01'
  const defaultEnd = '2026-07-02'
  try {
    let rows: KlineData[]
    if (source === 'main') {
      rows = await api.getMainContractKline(symbol, period, defaultStart, defaultEnd, limit, { signal: options.signal })
    } else {
      rows = []
    }

    if (rows.length > 0) {
      return { rows, period, notice: null }
    }

    return {
      rows,
      period,
      notice: `主力合约（${period}）暂无数据`,
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
