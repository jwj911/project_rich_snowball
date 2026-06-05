import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useKlineChart } from '@/hooks/useKlineChart'

// 每个测试独立的 mock 实例
function createMockChart() {
  const candleSeries = {
    setData: vi.fn(),
    priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
    coordinateToPrice: vi.fn(),
  }
  const volumeSeries = {
    setData: vi.fn(),
    priceScale: vi.fn(() => ({ applyOptions: vi.fn() })),
  }
  const timeScale = { fitContent: vi.fn() }
  const chart = {
    addSeries: vi.fn()
      .mockReturnValueOnce(candleSeries)
      .mockReturnValueOnce(volumeSeries),
    subscribeCrosshairMove: vi.fn(),
    unsubscribeCrosshairMove: vi.fn(),
    applyOptions: vi.fn(),
    remove: vi.fn(),
    timeScale: vi.fn(() => timeScale),
  }
  return { chart, candleSeries, volumeSeries, timeScale }
}

let currentMock: ReturnType<typeof createMockChart>

vi.mock('lightweight-charts', () => ({
  createChart: vi.fn(() => currentMock.chart),
  CandlestickSeries: vi.fn(),
  HistogramSeries: vi.fn(),
  ColorType: { Solid: 'solid' },
  CrosshairMode: { Normal: 0 },
  LineStyle: { Dashed: 2 },
}))

// mock ResizeObserver 为构造函数
type MockRObserverInstance = { _callback?: ResizeObserverCallback }
function MockResizeObserver(this: MockRObserverInstance, callback: ResizeObserverCallback) {
  this._callback = callback
}
MockResizeObserver.prototype.observe = vi.fn()
MockResizeObserver.prototype.disconnect = vi.fn()
MockResizeObserver.prototype.unobserve = vi.fn()

global.ResizeObserver = MockResizeObserver as unknown as typeof ResizeObserver

describe('useKlineChart', () => {
  let container: HTMLDivElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    currentMock = createMockChart()
    vi.clearAllMocks()
  })

  afterEach(() => {
    document.body.removeChild(container)
  })

  it('应在 chart 实例创建后灌入 pending 数据', async () => {
    // 先以 enabled=false 渲染，此时 chart 不会创建
    const { result, rerender } = renderHook(
      ({ enabled }) =>
        useKlineChart({
          containerRef: { current: container },
          enabled,
          pricePrecision: 2,
        }),
      { initialProps: { enabled: false } },
    )

    // chart 未创建时调用 setData，数据应被缓存
    const candleData = [{ time: '2024-01-01' as unknown as import('lightweight-charts').Time, open: 100, high: 110, low: 90, close: 105 }]
    const volumeData = [{ time: '2024-01-01' as unknown as import('lightweight-charts').Time, value: 1000, color: '#ff0000' }]

    act(() => {
      result.current.setData(candleData, volumeData)
    })

    // 此时 instanceRef 尚未创建
    expect(result.current.instanceRef.current).toBeNull()

    // 切换到 enabled=true，chart 应创建并自动灌入 pending 数据
    rerender({ enabled: true })

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10))
    })

    expect(currentMock.candleSeries.setData).toHaveBeenCalledWith(candleData)
    expect(currentMock.volumeSeries.setData).toHaveBeenCalledWith(volumeData)
    expect(currentMock.timeScale.fitContent).toHaveBeenCalled()
  })

  it('应在已有 chart 实例时直接灌入数据', async () => {
    const { result } = renderHook(() =>
      useKlineChart({
        containerRef: { current: container },
        enabled: true,
        pricePrecision: 2,
      }),
    )

    // 等待 chart 创建
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10))
    })

    // 已有 chart 实例后 setData 应直接执行
    const candleData = [{ time: '2024-01-02' as unknown as import('lightweight-charts').Time, open: 101, high: 111, low: 91, close: 106 }]
    const volumeData = [{ time: '2024-01-02' as unknown as import('lightweight-charts').Time, value: 1001, color: '#ff0000' }]

    act(() => {
      result.current.setData(candleData, volumeData)
    })

    expect(currentMock.candleSeries.setData).toHaveBeenCalledWith(candleData)
    expect(currentMock.volumeSeries.setData).toHaveBeenCalledWith(volumeData)
  })

  it('fitContent 应在 chart 就绪时调用 timeScale().fitContent()', async () => {
    const { result } = renderHook(() =>
      useKlineChart({
        containerRef: { current: container },
        enabled: true,
      }),
    )

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 10))
    })

    act(() => {
      result.current.fitContent()
    })

    expect(currentMock.timeScale.fitContent).toHaveBeenCalled()
  })
})
