'use client'

import { useCallback, useMemo, useRef, useState } from 'react'
import { Time } from 'lightweight-charts'
import EmptyState from '@/components/ui/EmptyState'
import LevelChips from '@/components/kline/LevelChips'
import KlineChartHeader from '@/components/kline/KlineChartHeader'
import CrosshairTooltip from '@/components/kline/CrosshairTooltip'
import AnnotationContextMenu from '@/components/kline/AnnotationContextMenu'
import { LineChart } from 'lucide-react'
import { formatPrice } from '@/lib/format'
import { CHART } from '@/lib/constants'
import { KlineData } from '@/lib/api'
import { AnnotationMenu, CandlePoint, CrosshairQuote, normalizeKlineData, maxOf, minOf } from '@/lib/klineChart'
import { useKlineChart } from '@/hooks/useKlineChart'
import { useKlinePriceLines } from '@/hooks/useKlinePriceLines'

interface KlineChartProps {
  data: KlineData[]
  symbol: string
  pricePrecision?: number
  supportLevels?: number[]
  resistanceLevels?: number[]
  onAddSupport?: (price: number) => void
  onAddResistance?: (price: number) => void
  onRemoveSupport?: (price: number) => void
  onRemoveResistance?: (price: number) => void
}

const CHART_HEIGHT = CHART.HEIGHT

export default function KlineChart({
  data: externalData,
  symbol,
  pricePrecision = 2,
  supportLevels = [],
  resistanceLevels = [],
  onAddSupport,
  onAddResistance,
  onRemoveSupport,
  onRemoveResistance,
}: KlineChartProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const pointByTimeRef = useRef<Map<Time, CandlePoint>>(new Map())

  const [annotationMenu, setAnnotationMenu] = useState<AnnotationMenu | null>(null)
  const [crosshairQuote, setCrosshairQuote] = useState<CrosshairQuote | null>(null)

  const points = useMemo(() => normalizeKlineData(externalData), [externalData])
  const pointByTime = useMemo(
    () => new Map(points.map((point) => [point.time, point])),
    [points],
  )
  const candleData = useMemo(
    () => points.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })),
    [points],
  )
  const volumeData = useMemo(
    () => points.map((point) => ({
      time: point.time,
      value: Math.max(point.volume, 0),
      color: point.close >= point.open ? `${CHART.UP_COLOR}61` : `${CHART.DOWN_COLOR}61`,
    })),
    [points],
  )
  const latestPoint = points[points.length - 1]
  const firstPoint = points[0]
  const hasChartData = points.length > 0

  const handleCrosshairMove = useCallback((time: Time | null, candleData: {
    open: number
    high: number
    low: number
    close: number
  } | null) => {
    if (!time || !candleData) {
      setCrosshairQuote(null)
      return
    }
    const matchedPoint = pointByTimeRef.current.get(time)
    setCrosshairQuote({
      time: matchedPoint?.originalTime ?? String(time),
      open: candleData.open,
      high: candleData.high,
      low: candleData.low,
      close: candleData.close,
      volume: matchedPoint?.volume ?? 0,
      contractCode: matchedPoint?.contractCode ?? null,
    })
  }, [])

  const { instanceRef, setData } = useKlineChart({
    containerRef: chartContainerRef,
    enabled: hasChartData,
    pricePrecision,
    onCrosshairMove: handleCrosshairMove,
  })

  useKlinePriceLines(instanceRef.current?.candleSeries ?? null, supportLevels, resistanceLevels)

  // Sync data to chart and pointByTime ref
  const prevPointsRef = useRef(points)
  if (prevPointsRef.current !== points) {
    prevPointsRef.current = points
    pointByTimeRef.current = pointByTime
    setData(candleData, volumeData)
  }

  const openAnnotationMenu = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    const root = rootRef.current
    const chartContainer = chartContainerRef.current
    const candleSeries = instanceRef.current?.candleSeries
    if (!root || !chartContainer || !candleSeries || (!onAddSupport && !onAddResistance)) return

    const chartRect = chartContainer.getBoundingClientRect()
    const rootRect = root.getBoundingClientRect()
    const price = candleSeries.coordinateToPrice(event.clientY - chartRect.top)
    if (!Number.isFinite(price)) return

    setAnnotationMenu({
      x: Math.min(Math.max(event.clientX - rootRect.left, 12), Math.max(rootRect.width - 172, 12)),
      y: Math.min(Math.max(event.clientY - rootRect.top, 48), CHART_HEIGHT - 96),
      price: Number(price),
    })
  }

  const closeAnnotationMenu = () => setAnnotationMenu(null)

  if (points.length === 0) {
    return (
      <div className="w-full rounded-lg border border-border bg-surface-inset p-4">
        <EmptyState
          icon={LineChart}
          title="暂无 K 线数据"
          description="当前品种还没有可展示的 K 线数据，等待数据同步后会自动展示。"
          className="border-border bg-surface-elevated"
        />
      </div>
    )
  }

  return (
    <div
      ref={rootRef}
      role="img"
      aria-label={`${symbol} K线图，最新价 ${formatPrice(latestPoint.close, pricePrecision)}，最高 ${formatPrice(maxOf(points, 'high'), pricePrecision)}，最低 ${formatPrice(minOf(points, 'low'), pricePrecision)}`}
      onContextMenu={openAnnotationMenu}
      onClick={annotationMenu ? closeAnnotationMenu : undefined}
      className="relative w-full select-none overflow-hidden rounded-lg border border-border bg-surface-inset"
    >
      <KlineChartHeader
        symbol={symbol}
        points={points}
        firstPoint={firstPoint}
        latestPoint={latestPoint}
        quote={crosshairQuote}
        pricePrecision={pricePrecision}
      />

      <div ref={chartContainerRef} className="h-[520px] w-full cursor-crosshair" />

      <CrosshairTooltip quote={crosshairQuote} latestPoint={latestPoint} pricePrecision={pricePrecision} />

      {(supportLevels.length > 0 || resistanceLevels.length > 0) && (
        <div className="absolute right-3 top-12 max-w-[220px] space-y-2 rounded border border-border bg-surface-elevated/95 p-2 text-xs shadow-lg">
          <LevelChips title="支撑" levels={supportLevels} tone="support" onRemove={onRemoveSupport} />
          <LevelChips title="阻力" levels={resistanceLevels} tone="resistance" onRemove={onRemoveResistance} />
        </div>
      )}

      {annotationMenu && (
        <AnnotationContextMenu
          menu={annotationMenu}
          canAddSupport={!!onAddSupport}
          canAddResistance={!!onAddResistance}
          onAddSupport={() => {
            if (annotationMenu && onAddSupport) onAddSupport(annotationMenu.price)
            closeAnnotationMenu()
          }}
          onAddResistance={() => {
            if (annotationMenu && onAddResistance) onAddResistance(annotationMenu.price)
            closeAnnotationMenu()
          }}
          onClose={closeAnnotationMenu}
        />
      )}
    </div>
  )
}
