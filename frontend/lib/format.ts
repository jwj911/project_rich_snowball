export function formatNumber(value: number | null | undefined, digits = 2) {
  if (!Number.isFinite(value)) return '--'
  return new Intl.NumberFormat('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value as number)
}

export function formatInteger(value: number | null | undefined) {
  if (!Number.isFinite(value)) return '--'
  return new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: 0,
  }).format(value as number)
}

export function formatPercent(value: number | null | undefined) {
  if (!Number.isFinite(value)) return '--'
  const numericValue = value as number
  const sign = numericValue > 0 ? '+' : ''
  return `${sign}${numericValue.toFixed(2)}%`
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return '--'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '--'
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function getChangeTone(value: number | null | undefined) {
  return (value ?? 0) >= 0 ? 'up' : 'down'
}
