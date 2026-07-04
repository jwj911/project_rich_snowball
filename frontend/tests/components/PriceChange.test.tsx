import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import PriceChange from '@/components/market/PriceChange'

describe('PriceChange', () => {
  it('renders positive change with + sign', () => {
    render(<PriceChange value={1.25} />)
    expect(screen.getByText('+1.25%')).toBeInTheDocument()
  })

  it('renders negative change without extra sign', () => {
    render(<PriceChange value={-0.5} />)
    expect(screen.getByText('-0.50%')).toBeInTheDocument()
  })

  it('renders zero as +0.00%', () => {
    render(<PriceChange value={0} />)
    expect(screen.getByText('+0.00%')).toBeInTheDocument()
  })

  it('renders -- with neutral class for null', () => {
    const { container } = render(<PriceChange value={null} />)
    expect(screen.getByText('--')).toBeInTheDocument()
    expect(container.querySelector('svg')).not.toBeInTheDocument()
    expect(screen.getByText('--').closest('span')).toHaveClass('text-gray-800')
  })

  it('renders -- with neutral class for undefined', () => {
    const { container } = render(<PriceChange value={undefined} />)
    expect(screen.getByText('--')).toBeInTheDocument()
    expect(container.querySelector('svg')).not.toBeInTheDocument()
    expect(screen.getByText('--').closest('span')).toHaveClass('text-gray-800')
  })

  it('hides icon when showIcon is false', () => {
    const { container } = render(<PriceChange value={1.25} showIcon={false} />)
    expect(container.querySelector('svg')).not.toBeInTheDocument()
  })
})
