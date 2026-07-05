export function formatNumber(value: number | null | undefined, digits = 2) {
  if (typeof value === 'string') {
    const parsed = Number(value)
    if (!Number.isFinite(parsed)) return '--'
    return new Intl.NumberFormat('zh-CN', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    }).format(parsed)
  }
  if (!Number.isFinite(value)) return '--'
  return new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value as number)
}

export function formatPrice(value: number | null | undefined, precision?: number | null) {
  return formatNumber(value, precision ?? 2)
}

export function formatInteger(value: number | null | undefined) {
  let numericValue: number
  if (typeof value === 'string') {
    numericValue = Number(value)
  } else {
    numericValue = value as number
  }
  if (!Number.isFinite(numericValue)) return '--'
  return new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: 0,
  }).format(numericValue)
}

export function formatPercent(value: number | null | undefined) {
  let numericValue: number
  if (typeof value === 'string') {
    numericValue = Number(value)
  } else {
    numericValue = value as number
  }
  if (!Number.isFinite(numericValue)) return '--'
  const sign = numericValue >= 0 ? '+' : ''
  return `${sign}${numericValue.toFixed(2)}%`
}

export function formatDateOnly(value: string | null | undefined) {
  if (!value) return '--'
  // 后端 trade_date 是 DateTime 序列化的 ISO 字符串（如 "2026-07-03T00:00:00Z"），
  // 也可能是纯日期字符串。统一解析后按东八区格式化。
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(date).replace(/\//g, '-')
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(date)
}

export function formatRelativeTime(value: string | null | undefined) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'

  const seconds = Math.max(0, Math.floor((Date.now() - date.getTime()) / 1000))
  if (seconds < 60) return `${seconds} 秒前`

  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes} 分钟前`

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours} 小时前`

  return `${Math.floor(hours / 24)} 天前`
}

export function getChangeTone(value: number | null | undefined): 'up' | 'down' | 'neutral' {
  if (value == null) return 'neutral'
  return value >= 0 ? 'up' : 'down'
}

export function formatPricePayload(price: number, precision = 2): string {
  if (!Number.isFinite(price)) throw new Error('Invalid price for payload')
  return price.toFixed(precision)
}

export function isLimitUp(price: number | null | undefined, limitUp: number | null | undefined, epsilon = 0.01) {
  return limitUp != null && price != null && Math.abs(price - limitUp) < epsilon
}

export function isLimitDown(price: number | null | undefined, limitDown: number | null | undefined, epsilon = 0.01) {
  return limitDown != null && price != null && Math.abs(price - limitDown) < epsilon
}
