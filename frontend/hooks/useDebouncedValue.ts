'use client'

import { useEffect, useState } from 'react'

/**
 * 将输入值延迟一定时间后再输出。
 * 适用于搜索框等场景，避免每次输入都触发请求。
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedValue(value)
    }, delayMs)
    return () => {
      window.clearTimeout(timer)
    }
  }, [value, delayMs])

  return debouncedValue
}
