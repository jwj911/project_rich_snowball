import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import QuoteCard from '@/components/market/QuoteCard'
import { Product } from '@/lib/api'

const mockProduct: Product = {
  id: 1,
  name: '螺纹钢主力',
  symbol: 'RB2501',
  current_price: 3500.5,
  change_percent: 1.25,
  open_price: 3450,
  high: 3520,
  low: 3440,
  volume: 1234567,
  category: '黑色金属',
  margin: 10,
  commission: 5,
  updated_at: '2026-05-22T08:00:00.000Z',
}

describe('QuoteCard', () => {
  it('renders product name and symbol', () => {
    render(<QuoteCard product={mockProduct} />)
    expect(screen.getByText('螺纹钢主力')).toBeInTheDocument()
    expect(screen.getByText('RB2501')).toBeInTheDocument()
  })

  it('renders formatted price with 2 decimals', () => {
    render(<QuoteCard product={mockProduct} />)
    expect(screen.getByText('3,500.50')).toBeInTheDocument()
  })

  it('renders placeholder for null price', () => {
    const noPrice = { ...mockProduct, current_price: null }
    render(<QuoteCard product={noPrice} />)
    expect(screen.getByText('--')).toBeInTheDocument()
  })

  it('renders category label', () => {
    render(<QuoteCard product={mockProduct} />)
    expect(screen.getByText('黑色金属')).toBeInTheDocument()
  })

  it('links to product detail page', () => {
    render(<QuoteCard product={mockProduct} />)
    const link = screen.getByRole('link')
    expect(link).toHaveAttribute('href', '/products/1')
  })
})
