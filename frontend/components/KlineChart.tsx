'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  IChartApi,
  IPriceLine,
  ISeriesApi,
  LineStyle,
  Time,
  UTCTimestamp,
  createChart,
} from 'lightweight-charts'
import EmptyState from '@/components/ui/EmptyState'
import { LineChart } from 'lucide-react'

interface KlineData {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

interface KlineChartProps {
  data: KlineData[]
  symbol: string
  supportLevels?: number[]
  resistanceLevels?: number[]
  onAddSupport?: (price: number) => void
  onAddResistance?: (price: number) => void
  onRemoveSupport?: (price: number) => void
  onRemoveResistance?: (price: number) => void
}

interface AnnotationMenu {
  x: number
  y: number
  price: number
}

interface CrosshairQuote {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

type CandlePoint = {
  time: Time
  originalTime: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

const CHART_HEIGHT = 520
const SUPPORT_COLOR = '#4ade80'
const RESISTANCE_COLOR = '#ff6b6b'
const UP_COLOR = '#ff6b6b'
const DOWN_COLOR = '#4ade80'

export default function KlineChart({
  data: externalData,
  symbol,
  supportLevels = [],
  resistanceLevels = [],
  onAddSupport,
  onAddResistance,
  onRemoveSupport,
  onRemoveResistance,
}: KlineChartProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const priceLinesRef = useRef<IPriceLine[]>([])

  const [annotationMenu, setAnnotationMenu] = useState<AnnotationMenu | null>(null)
  const [crosshairQuote, setCrosshairQuote] = useState<CrosshairQuote | null>(null)

  const points = useMemo(() => normalizeKlineData(externalData), [externalData])
  const latestPoint = points[points.length - 1]
  const firstPoint = points[0]

  useEffect(() => {
    const container = chartContainerRef.current
    if (!container || points.length === 0) return

    const chart = createChart(container, {
      width: container.clientWidth,
      height: CHART_HEIGHT,
      layout: {
        background: { type: ColorType.Solid, color: '#131722' },
        textColor: '#94a3b8',
        fontFamily: 'JetBrains Mono, Consolas, monospace',
      },
      grid: {
        vertLines: { color: '#263244' },
        horzLines: { color: '#263244' },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: '#64748b', style: LineStyle.Dashed, labelBackgroundColor: '#1e293b' },
        horzLine: { color: '#64748b', style: LineStyle.Dashed, labelBackgroundColor: '#1e293b' },
      },
      rightPriceScale: {
        borderColor: '#263244',
        scaleMargins: { top: 0.08, bottom: 0.25 },
      },
      timeScale: {
        borderColor: '#263244',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 6,
        barSpacing: 8,
      },
      localization: {
        priceFormatter: (price: number) => price.toFixed(2),
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
      },
      handleScroll: {
        horzTouchDrag: true,
        mouseWheel: true,
        pressedMouseMove: true,
        vertTouchDrag: false,
      },
    })

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: UP_COLOR,
      downColor: DOWN_COLOR,
      borderUpColor: UP_COLOR,
      borderDownColor: DOWN_COLOR,
      wickUpColor: UP_COLOR,
      wickDownColor: DOWN_COLOR,
      priceLineColor: '#f8fafc',
      lastValueVisible: true,
      priceLineVisible: true,
    })
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: '',
      lastValueVisible: false,
      priceLineVisible: false,
    })

    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries

    const handleCrosshairMove = (param: Parameters<IChartApi['subscribeCrosshairMove']>[0] extends (arg: infer P) => void ? P : never) => {
      const seriesData = param.seriesData.get(candleSeries)
      if (!seriesData || !('open' in seriesData)) {
        setCrosshairQuote(null)
        return
      }

      const matchedPoint = points.find((point) => point.time === seriesData.time)
      setCrosshairQuote({
        time: matchedPoint?.originalTime ?? String(seriesData.time),
        open: seriesData.open,
        high: seriesData.high,
        low: seriesData.low,
        close: seriesData.close,
        volume: matchedPoint?.volume ?? 0,
      })
    }

    const resizeObserver = new ResizeObserver(([entry]) => {
      const width = Math.floor(entry.contentRect.width)
      if (width > 0) {
        chart.applyOptions({ width, height: CHART_HEIGHT })
      }
    })

    chart.subscribeCrosshairMove(handleCrosshairMove)
    resizeObserver.observe(container)

    return () => {
      chart.unsubscribeCrosshairMove(handleCrosshairMove)
      resizeObserver.disconnect()
      chart.remove()
      chartRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
      priceLinesRef.current = []
    }
  }, [points])

  useEffect(() => {
    const candleSeries = candleSeriesRef.current
    const volumeSeries = volumeSeriesRef.current
    const chart = chartRef.current
    if (!candleSeries || !volumeSeries || !chart || points.length === 0) return

    candleSeries.setData(points.map(({ time, open, high, low, close }) => ({ time, open, high, low, close })))
    volumeSeries.setData(points.map((point) => ({
      time: point.time,
      value: Math.max(point.volume, 0),
      color: point.close >= point.open ? 'rgba(255, 107, 107, 0.38)' : 'rgba(74, 222, 128, 0.38)',
    })))
    chart.timeScale().fitContent()
  }, [points])

  useEffect(() => {
    const candleSeries = candleSeriesRef.current
    if (!candleSeries) return

    priceLinesRef.current.forEach((line) => candleSeries.removePriceLine(line))
    priceLinesRef.current = []

    const addLine = (price: number, type: 'support' | 'resistance') => {
      if (!Number.isFinite(price)) return

      priceLinesRef.current.push(candleSeries.createPriceLine({
        price,
        color: type === 'support' ? SUPPORT_COLOR : RESISTANCE_COLOR,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: type === 'support' ? '支撑' : '阻力',
      }))
    }

    supportLevels.forEach((price) => addLine(price, 'support'))
    resistanceLevels.forEach((price) => addLine(price, 'resistance'))
  }, [resistanceLevels, supportLevels, points])

  const latestColor = latestPoint && firstPoint && latestPoint.close >= firstPoint.open ? 'text-red-400' : 'text-green-400'

  const openAnnotationMenu = (event: React.MouseEvent<HTMLDivElement>) => {
    event.preventDefault()
    const root = rootRef.current
    const chartContainer = chartContainerRef.current
    const candleSeries = candleSeriesRef.current
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

  const addSupportFromMenu = () => {
    if (annotationMenu && onAddSupport) {
      onAddSupport(annotationMenu.price)
    }
    closeAnnotationMenu()
  }

  const addResistanceFromMenu = () => {
    if (annotationMenu && onAddResistance) {
      onAddResistance(annotationMenu.price)
    }
    closeAnnotationMenu()
  }

  if (points.length === 0) {
    return (
      <div className="w-full rounded-lg border border-[#2a2e39] bg-[#131722] p-4">
        <EmptyState
          icon={LineChart}
          title="暂无 K 线数据"
          description="当前品种还没有可展示的 K 线数据，等待数据同步后会自动展示。"
          className="border-[#2a2e39] bg-[#1e222d]"
        />
      </div>
    )
  }

  return (
    <div
      ref={rootRef}
      onContextMenu={openAnnotationMenu}
      onClick={annotationMenu ? closeAnnotationMenu : undefined}
      className="relative w-full select-none overflow-hidden rounded-lg border border-[#2a2e39] bg-[#131722]"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-[#2a2e39] px-3 py-2 text-xs text-slate-400">
        <span className="mr-auto font-semibold text-white">{symbol}</span>
        <span>
          最新 <span className={`font-mono ${latestColor}`}>{latestPoint.close.toFixed(2)}</span>
        </span>
        <span>开 <span className="font-mono text-slate-200">{(crosshairQuote?.open ?? firstPoint.open).toFixed(2)}</span></span>
        <span>高 <span className="font-mono text-red-300">{(crosshairQuote?.high ?? maxOf(points, 'high')).toFixed(2)}</span></span>
        <span>低 <span className="font-mono text-green-300">{(crosshairQuote?.low ?? minOf(points, 'low')).toFixed(2)}</span></span>
      </div>

      <div ref={chartContainerRef} className="h-[520px] w-full cursor-crosshair" />

      <div className="absolute left-3 top-12 rounded border border-[#2a2e39] bg-[#1e222d]/95 px-3 py-2 text-xs shadow-lg">
        <div className="grid grid-cols-[42px_minmax(72px,auto)] gap-x-3 gap-y-1">
          <span className="text-slate-500">时间</span>
          <span className="font-mono text-slate-200">{crosshairQuote?.time ?? latestPoint.originalTime}</span>
          <span className="text-slate-500">收盘</span>
          <span className="font-mono text-slate-200">{(crosshairQuote?.close ?? latestPoint.close).toFixed(2)}</span>
          <span className="text-slate-500">成交量</span>
          <span className="font-mono text-slate-200">{Math.round(crosshairQuote?.volume ?? latestPoint.volume).toLocaleString()}</span>
        </div>
      </div>

      {(supportLevels.length > 0 || resistanceLevels.length > 0) && (
        <div className="absolute right-3 top-12 max-w-[220px] space-y-2 rounded border border-[#2a2e39] bg-[#1e222d]/95 p-2 text-xs shadow-lg">
          <LevelChips title="支撑" levels={supportLevels} tone="support" onRemove={onRemoveSupport} />
          <LevelChips title="阻力" levels={resistanceLevels} tone="resistance" onRemove={onRemoveResistance} />
        </div>
      )}

      {annotationMenu && (
        <div
          className="absolute z-20 w-40 rounded-lg border border-[#2a2e39] bg-[#1e222d] p-2 text-xs shadow-xl"
          style={{ left: annotationMenu.x, top: annotationMenu.y }}
          onClick={(event) => event.stopPropagation()}
        >
          <div className="mb-2 border-b border-[#2a2e39] pb-2 font-mono text-slate-200">
            {annotationMenu.price.toFixed(2)}
          </div>
          <button
            type="button"
            onClick={addSupportFromMenu}
            disabled={!onAddSupport}
            className="flex w-full items-center justify-between rounded px-2 py-2 text-left text-green-300 transition hover:bg-green-400/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            添加支撑位
            <span className="h-2 w-2 rounded-full bg-green-400" />
          </button>
          <button
            type="button"
            onClick={addResistanceFromMenu}
            disabled={!onAddResistance}
            className="mt-1 flex w-full items-center justify-between rounded px-2 py-2 text-left text-red-300 transition hover:bg-red-400/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            添加阻力位
            <span className="h-2 w-2 rounded-full bg-red-400" />
          </button>
          <button
            type="button"
            onClick={closeAnnotationMenu}
            className="mt-1 w-full rounded px-2 py-2 text-left text-slate-400 transition hover:bg-slate-700/40 hover:text-slate-200"
          >
            取消
          </button>
        </div>
      )}
    </div>
  )
}

function LevelChips({
  title,
  levels,
  tone,
  onRemove,
}: {
  title: string
  levels: number[]
  tone: 'support' | 'resistance'
  onRemove?: (price: number) => void
}) {
  if (levels.length === 0) return null

  const colorClass = tone === 'support'
    ? 'border-green-400/30 bg-green-400/10 text-green-300'
    : 'border-red-400/30 bg-red-400/10 text-red-300'

  return (
    <div>
      <div className="mb-1 text-slate-500">{title}</div>
      <div className="flex flex-wrap gap-1">
        {levels.map((level) => (
          <button
            key={`${tone}-${level}`}
            type="button"
            onClick={() => onRemove?.(level)}
            className={`rounded border px-1.5 py-1 font-mono transition hover:bg-slate-700/40 ${colorClass}`}
            title="点击删除"
          >
            {level.toFixed(2)}
          </button>
        ))}
      </div>
    </div>
  )
}

function normalizeKlineData(data: KlineData[]): CandlePoint[] {
  const byTime = new Map<number, CandlePoint>()

  data.forEach((item) => {
    const timestamp = parseTimestamp(item.time)
    if (timestamp === null) return

    const open = Number(item.open)
    const high = Number(item.high)
    const low = Number(item.low)
    const close = Number(item.close)
    const volume = Number(item.volume)

    if (![open, high, low, close].every(Number.isFinite)) return

    const safeHigh = Math.max(high, open, close, low)
    const safeLow = Math.min(low, open, close, high)

    byTime.set(timestamp, {
      time: timestamp as UTCTimestamp,
      originalTime: item.time,
      open,
      high: safeHigh,
      low: safeLow,
      close,
      volume: Number.isFinite(volume) ? Math.max(volume, 0) : 0,
    })
  })

  return Array.from(byTime.values()).sort((a, b) => Number(a.time) - Number(b.time))
}

function parseTimestamp(value: string): number | null {
  const trimmed = value.trim()
  if (!trimmed) return null

  const numeric = Number(trimmed)
  if (Number.isFinite(numeric) && numeric > 0) {
    return Math.floor(numeric > 10_000_000_000 ? numeric / 1000 : numeric)
  }

  const parsed = Date.parse(trimmed)
  if (!Number.isFinite(parsed)) return null

  return Math.floor(parsed / 1000)
}

function maxOf(points: CandlePoint[], key: 'high' | 'low') {
  return Math.max(...points.map((point) => point[key]))
}

function minOf(points: CandlePoint[], key: 'high' | 'low') {
  return Math.min(...points.map((point) => point[key]))
}
