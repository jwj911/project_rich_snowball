'use client'

import { RefObject, useCallback, useState } from 'react'
import { ISeriesApi } from 'lightweight-charts'
import { AnnotationMenu, CHART_HEIGHT } from '@/lib/klineChart'

interface UseAnnotationMenuOptions {
  rootRef: RefObject<HTMLDivElement | null>
  chartContainerRef: RefObject<HTMLDivElement | null>
  candleSeriesRef: RefObject<ISeriesApi<'Candlestick'> | null>
  onAddSupport?: (price: number) => void
  onAddResistance?: (price: number) => void
}

export function useAnnotationMenu({
  rootRef,
  chartContainerRef,
  candleSeriesRef,
  onAddSupport,
  onAddResistance,
}: UseAnnotationMenuOptions) {
  const [annotationMenu, setAnnotationMenu] = useState<AnnotationMenu | null>(null)

  const closeAnnotationMenu = useCallback(() => {
    setAnnotationMenu(null)
  }, [])

  const openAnnotationMenu = useCallback((event: React.MouseEvent<HTMLDivElement>) => {
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
  }, [candleSeriesRef, chartContainerRef, onAddResistance, onAddSupport, rootRef])

  const addSupportFromMenu = useCallback(() => {
    if (annotationMenu && onAddSupport) {
      onAddSupport(annotationMenu.price)
    }
    closeAnnotationMenu()
  }, [annotationMenu, closeAnnotationMenu, onAddSupport])

  const addResistanceFromMenu = useCallback(() => {
    if (annotationMenu && onAddResistance) {
      onAddResistance(annotationMenu.price)
    }
    closeAnnotationMenu()
  }, [annotationMenu, closeAnnotationMenu, onAddResistance])

  return {
    annotationMenu,
    openAnnotationMenu,
    closeAnnotationMenu,
    addSupportFromMenu,
    addResistanceFromMenu,
  }
}
