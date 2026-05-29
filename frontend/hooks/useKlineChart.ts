'use client'

import { RefObject, useEffect, useRef } from 'react'
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  IChartApi,
  ISeriesApi,
  LineStyle,
  Time,
  createChart,
} from 'lightweight-charts'
import { CHART } from '@/lib/constants'

const CHART_HEIGHT = CHART.HEIGHT
const UP_COLOR = CHART.UP_COLOR
const DOWN_COLOR = CHART.DOWN_COLOR

export interface KlineChartInstance {
  chart: IChartApi
  candleSeries: ISeriesApi<'Candlestick'>
  volumeSeries: ISeriesApi<'Histogram'>
}

interface UseKlineChartOptions {
  containerRef: RefObject<HTMLDivElement | null>
  enabled: boolean
  pricePrecision?: number
  onCrosshairMove?: (time: Time | null, candleData: {
    open: number
    high: number
    low: number
    close: number
  } | null) => void
}

export function useKlineChart({ containerRef, enabled, pricePrecision = 2, onCrosshairMove }: UseKlineChartOptions) {
  const instanceRef = useRef<KlineChartInstance | null>(null)
  const hasFitInitialContentRef = useRef(false)

  useEffect(() => {
    const container = containerRef.current
    if (!container || !enabled || instanceRef.current) return

    const chart = createChart(container, {
      width: container.clientWidth,
      height: CHART_HEIGHT,
      layout: {
        background: { type: ColorType.Solid, color: CHART.BG_COLOR },
        textColor: CHART.TEXT_COLOR,
        fontFamily: 'JetBrains Mono, Consolas, monospace',
      },
      grid: {
        vertLines: { color: CHART.GRID_COLOR },
        horzLines: { color: CHART.GRID_COLOR },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: CHART.CROSSHAIR_COLOR, style: LineStyle.Dashed, labelBackgroundColor: CHART.TOOLTIP_BG },
        horzLine: { color: CHART.CROSSHAIR_COLOR, style: LineStyle.Dashed, labelBackgroundColor: CHART.TOOLTIP_BG },
      },
      rightPriceScale: {
        borderColor: CHART.GRID_COLOR,
        scaleMargins: { top: 0.08, bottom: 0.25 },
      },
      timeScale: {
        borderColor: CHART.GRID_COLOR,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 6,
        barSpacing: 8,
      },
      localization: {
        priceFormatter: (price: number) => price.toFixed(pricePrecision),
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
      priceLineColor: CHART.TEXT_COLOR,
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

    instanceRef.current = { chart, candleSeries, volumeSeries }

    const handleCrosshairMove = (param: Parameters<IChartApi['subscribeCrosshairMove']>[0] extends (arg: infer P) => void ? P : never) => {
      const seriesData = param.seriesData.get(candleSeries)
      if (!seriesData || !('open' in seriesData)) {
        onCrosshairMove?.(null, null)
        return
      }
      onCrosshairMove?.(seriesData.time, {
        open: seriesData.open,
        high: seriesData.high,
        low: seriesData.low,
        close: seriesData.close,
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
      instanceRef.current = null
      hasFitInitialContentRef.current = false
    }
  }, [containerRef, enabled, onCrosshairMove, pricePrecision])

  const setData = (candleData: Array<{
    time: Time
    open: number
    high: number
    low: number
    close: number
  }>, volumeData: Array<{ time: Time; value: number; color: string }>) => {
    const instance = instanceRef.current
    if (!instance) return

    instance.candleSeries.setData(candleData)
    instance.volumeSeries.setData(volumeData)

    if (candleData.length > 0 && !hasFitInitialContentRef.current) {
      instance.chart.timeScale().fitContent()
      hasFitInitialContentRef.current = true
    }
  }

  return { instanceRef, setData }
}
