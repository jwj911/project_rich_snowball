'use client'

import { ReactNode, useEffect, useRef, useState } from 'react'

type Direction = 'up' | 'down' | null

interface PriceFlashProps {
  value: number | null | undefined
  children: ReactNode
  className?: string
}

export default function PriceFlash({ value, children, className = '' }: PriceFlashProps) {
  const previousValueRef = useRef(value)
  const [direction, setDirection] = useState<Direction>(null)

  useEffect(() => {
    if (value == null || previousValueRef.current == null || value === previousValueRef.current) {
      previousValueRef.current = value
      return
    }

    setDirection(value > previousValueRef.current ? 'up' : 'down')
    previousValueRef.current = value

    const timer = window.setTimeout(() => setDirection(null), 700)
    return () => window.clearTimeout(timer)
  }, [value])

  const flashClass = direction === 'up'
    ? 'animate-price-flash-up'
    : direction === 'down'
      ? 'animate-price-flash-down'
      : ''

  return (
    <span className={`rounded px-1 transition-colors ${flashClass} ${className}`}>
      {children}
    </span>
  )
}
