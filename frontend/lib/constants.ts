export const MARKET = {
  POLL_INTERVAL_MS: 30_000,
  SSE_RETRY_DELAY_MS: 3_000,
  SSE_FALLBACK_INTERVAL_MS: 10_000,
  STALE_THRESHOLD_MS: 60_000,
  DANGER_THRESHOLD_MS: 300_000,
} as const

export const CHART = {
  HEIGHT: 520,
  PRICE_DIGITS: 2,
} as const

export const KLINE = {
  SHORT_PERIOD_LIMIT: 120,   // 1m/5m/15m/30m
  MEDIUM_PERIOD_LIMIT: 100,  // 1h
  LONG_PERIOD_LIMIT: 90,     // 1d/1w
} as const

export const API = {
  TIMEOUT_MS: 15_000,
} as const
