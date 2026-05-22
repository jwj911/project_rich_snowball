import { act, renderHook } from '@testing-library/react'
import { RefObject } from 'react'
import { ISeriesApi } from 'lightweight-charts'
import { describe, expect, it, vi } from 'vitest'
import { useAnnotationMenu } from '@/hooks/useAnnotationMenu'

function elementWithRect(rect: Partial<DOMRect>): HTMLDivElement {
  return {
    getBoundingClientRect: () => ({
      x: 0,
      y: 0,
      width: 300,
      height: 520,
      top: 0,
      right: 300,
      bottom: 520,
      left: 0,
      toJSON: () => ({}),
      ...rect,
    }),
  } as HTMLDivElement
}

function candleSeriesRef(price: number): RefObject<ISeriesApi<'Candlestick'> | null> {
  return {
    current: {
      coordinateToPrice: vi.fn().mockReturnValue(price),
    } as unknown as ISeriesApi<'Candlestick'>,
  }
}

describe('useAnnotationMenu', () => {
  it('opens a clamped menu from chart coordinates and adds support', () => {
    const onAddSupport = vi.fn()
    const rootRef = { current: elementWithRect({ left: 10, top: 20, width: 300 }) }
    const chartContainerRef = { current: elementWithRect({ left: 10, top: 60, width: 300 }) }
    const seriesRef = candleSeriesRef(3650.25)

    const { result } = renderHook(() => useAnnotationMenu({
      rootRef,
      chartContainerRef,
      candleSeriesRef: seriesRef,
      onAddSupport,
    }))

    act(() => {
      result.current.openAnnotationMenu({
        preventDefault: vi.fn(),
        clientX: 500,
        clientY: 120,
      } as unknown as React.MouseEvent<HTMLDivElement>)
    })

    expect(result.current.annotationMenu).toEqual({
      x: 128,
      y: 100,
      price: 3650.25,
    })

    act(() => {
      result.current.addSupportFromMenu()
    })

    expect(onAddSupport).toHaveBeenCalledWith(3650.25)
    expect(result.current.annotationMenu).toBeNull()
  })

  it('ignores non-finite chart prices', () => {
    const rootRef = { current: elementWithRect({}) }
    const chartContainerRef = { current: elementWithRect({}) }
    const seriesRef = candleSeriesRef(Number.NaN)

    const { result } = renderHook(() => useAnnotationMenu({
      rootRef,
      chartContainerRef,
      candleSeriesRef: seriesRef,
      onAddResistance: vi.fn(),
    }))

    act(() => {
      result.current.openAnnotationMenu({
        preventDefault: vi.fn(),
        clientX: 20,
        clientY: 40,
      } as unknown as React.MouseEvent<HTMLDivElement>)
    })

    expect(result.current.annotationMenu).toBeNull()
  })
})
