'use client'

import { Dispatch, RefObject, SetStateAction, useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  IChartApi,
  ISeriesApi,
  LineStyle,
  createChart,
} from 'lightweight-charts'
import {
  CHART_HEIGHT,
  CandlePoint,
  CrosshairQuote,
  DOWN_COLOR,
  UP_COLOR,
} from '@/lib/klineChart'

interface UseLightweightChartOptions {
  containerRef: RefObject<HTMLDivElement | null>
  hasChartData: boolean
  candleData: Array<Pick<CandlePoint, 'time' | 'open' | 'high' | 'low' | 'close'>>
  volumeData: Array<{ time: CandlePoint['time']; value: number; color: string }>
  pointByTime: Map<CandlePoint['time'], CandlePoint>
  viewportResetKey?: string
  setCrosshairQuote: Dispatch<SetStateAction<CrosshairQuote | null>>
}

export function useLightweightChart({
  containerRef,
  hasChartData,
  candleData,
  volumeData,
  pointByTime,
  viewportResetKey,
  setCrosshairQuote,
}: UseLightweightChartOptions) {
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const pointByTimeRef = useRef<Map<CandlePoint['time'], CandlePoint>>(new Map())
  const hasFitInitialContentRef = useRef(false)

  useEffect(() => {
    pointByTimeRef.current = pointByTime
  }, [pointByTime])

  useEffect(() => {
    hasFitInitialContentRef.current = false
  }, [viewportResetKey])

  useEffect(() => {
    const container = containerRef.current
    if (!container || !hasChartData || chartRef.current) return

    let disposed = false

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
      if (disposed) return
      const seriesData = param.seriesData.get(candleSeries)
      if (!seriesData || !('open' in seriesData)) {
        setCrosshairQuote(null)
        return
      }

      const matchedPoint = pointByTimeRef.current.get(seriesData.time)
      setCrosshairQuote({
        time: matchedPoint?.originalTime ?? String(seriesData.time),
        open: seriesData.open,
        high: seriesData.high,
        low: seriesData.low,
        close: seriesData.close,
        volume: matchedPoint?.volume ?? 0,
        contractCode: matchedPoint?.contractCode ?? null,
      })
    }

    const resizeObserver = new ResizeObserver(([entry]) => {
      if (disposed) return
      const width = Math.floor(entry.contentRect.width)
      if (width > 0) {
        chart.applyOptions({ width, height: CHART_HEIGHT })
      }
    })

    chart.subscribeCrosshairMove(handleCrosshairMove)
    resizeObserver.observe(container)

    return () => {
      disposed = true
      chart.unsubscribeCrosshairMove(handleCrosshairMove)
      resizeObserver.disconnect()
      chartRef.current = null
      candleSeriesRef.current = null
      volumeSeriesRef.current = null
      hasFitInitialContentRef.current = false
      // 延迟 remove 到下一个事件循环，让 lightweight-charts 内部 pending 的
      // ResizeObserver / requestAnimationFrame 回调在 binding 被 dispose 之前先执行完
      setTimeout(() => {
        chart.remove()
      }, 0)
    }
  }, [containerRef, hasChartData, setCrosshairQuote])

  useEffect(() => {
    const candleSeries = candleSeriesRef.current
    const volumeSeries = volumeSeriesRef.current
    const chart = chartRef.current
    if (!candleSeries || !volumeSeries || !chart) return

    candleSeries.setData(candleData)
    volumeSeries.setData(volumeData)

    if (candleData.length > 0 && !hasFitInitialContentRef.current) {
      chart.timeScale().fitContent()
      hasFitInitialContentRef.current = true
    }
  }, [candleData, volumeData])

  return {
    chartRef,
    candleSeriesRef,
  }
}
