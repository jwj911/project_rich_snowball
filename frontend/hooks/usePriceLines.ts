'use client'

import { RefObject, useEffect, useRef } from 'react'
import { IPriceLine, ISeriesApi, LineStyle } from 'lightweight-charts'
import { RESISTANCE_COLOR, SUPPORT_COLOR } from '@/lib/klineChart'

export function usePriceLines(
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>,
  supportLevels: number[],
  resistanceLevels: number[],
) {
  const priceLinesRef = useRef<IPriceLine[]>([])

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

    return () => {
      priceLinesRef.current.forEach((line) => candleSeries.removePriceLine(line))
      priceLinesRef.current = []
    }
  }, [candleSeriesRef, resistanceLevels, supportLevels])
}
