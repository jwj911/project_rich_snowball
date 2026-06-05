import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'

describe('useDebouncedValue', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('应在初始时立即返回传入值', () => {
    const { result } = renderHook(() => useDebouncedValue('hello', 250))
    expect(result.current).toBe('hello')
  })

  it('应在延迟后才更新值', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 250),
      { initialProps: { value: 'a' } },
    )

    expect(result.current).toBe('a')

    rerender({ value: 'abc' })
    expect(result.current).toBe('a') // 尚未延迟

    act(() => {
      vi.advanceTimersByTime(249)
    })
    expect(result.current).toBe('a') // 还差 1ms

    act(() => {
      vi.advanceTimersByTime(1)
    })
    expect(result.current).toBe('abc') // 延迟到达
  })

  it('应在快速连续输入时只保留最后一次', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 250),
      { initialProps: { value: '' } },
    )

    rerender({ value: 'h' })
    act(() => { vi.advanceTimersByTime(100) })

    rerender({ value: 'he' })
    act(() => { vi.advanceTimersByTime(100) })

    rerender({ value: 'hel' })
    act(() => { vi.advanceTimersByTime(100) })

    // 前两次的 timer 已被清理，第三次还差 50ms
    expect(result.current).toBe('')

    rerender({ value: 'hell' })
    act(() => { vi.advanceTimersByTime(100) })

    rerender({ value: 'hello' })
    act(() => { vi.advanceTimersByTime(250) })

    // 最终只应得到最后一次输入
    expect(result.current).toBe('hello')
  })

  it('应支持不同的延迟时间', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 500),
      { initialProps: { value: 'x' } },
    )

    rerender({ value: 'y' })
    act(() => { vi.advanceTimersByTime(499) })
    expect(result.current).toBe('x')

    act(() => { vi.advanceTimersByTime(1) })
    expect(result.current).toBe('y')
  })

  it('应支持非字符串类型', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebouncedValue(value, 100),
      { initialProps: { value: 1 } },
    )

    rerender({ value: 2 })
    act(() => { vi.advanceTimersByTime(100) })
    expect(result.current).toBe(2)
  })
})
