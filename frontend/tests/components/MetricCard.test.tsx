import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import MetricCard from '@/components/ui/MetricCard'

describe('MetricCard', () => {
  it('maps market tones to fixed semantic color classes', () => {
    const { rerender } = render(<MetricCard label="上涨" value="12" tone="up" />)

    expect(screen.getByText('12')).toHaveClass('text-red-400')

    rerender(<MetricCard label="下跌" value="8" tone="down" />)

    expect(screen.getByText('8')).toHaveClass('text-green-400')
  })

  it('uses neutral text by default', () => {
    render(<MetricCard label="品种数" value="32" />)

    expect(screen.getByText('32')).toHaveClass('text-slate-200')
  })
})
