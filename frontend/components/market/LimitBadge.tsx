interface LimitBadgeProps {
  limitUp: number | null | undefined
  limitDown: number | null | undefined
  currentPrice: number | null | undefined
}

function isNearLimit(price: number, limit: number | null | undefined): boolean {
  if (limit == null || !Number.isFinite(price)) return false
  return Math.abs(price - limit) < 0.01
}

export default function LimitBadge({ limitUp, limitDown, currentPrice }: LimitBadgeProps) {
  if (!Number.isFinite(currentPrice)) return null

  if (isNearLimit(currentPrice, limitUp)) {
    return (
      <span className="rounded bg-red-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
        涨停
      </span>
    )
  }

  if (isNearLimit(currentPrice, limitDown)) {
    return (
      <span className="rounded bg-green-600 px-1.5 py-0.5 text-[10px] font-bold text-white">
        跌停
      </span>
    )
  }

  return null
}
