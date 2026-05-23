import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import QuoteTable from '@/components/market/QuoteTable'
import { Product } from '@/lib/api'

function makeProduct(id: number, overrides: Partial<Product> = {}): Product {
  return {
    id,
    name: `品种${id}`,
    symbol: `P${id}`,
    current_price: 100 + id,
    change_percent: id % 2 === 0 ? 1.2 : -0.8,
    open_price: 100,
    high: 110,
    low: 90,
    volume: id * 1000,
    category: '测试',
    margin: null,
    commission: null,
    updated_at: '2026-05-16T10:00:00',
    ...overrides,
  }
}

describe('QuoteTable', () => {
  it('renders product rows in table', () => {
    const products = [makeProduct(1), makeProduct(2)]

    render(
      <QuoteTable
        products={products}
        sortBy="change_percent"
        sortOrder="desc"
        onSort={vi.fn()}
      />,
    )

    const table = screen.getByRole('table')
    expect(within(table).getByText('品种1')).toBeInTheDocument()
    expect(within(table).getByText('品种2')).toBeInTheDocument()
    expect(within(table).getByText('P1')).toBeInTheDocument()
    expect(within(table).getByText('P2')).toBeInTheDocument()
  })

  it('emits sort changes when clicking column headers', () => {
    const onSort = vi.fn()

    render(
      <QuoteTable
        products={[makeProduct(1), makeProduct(2)]}
        sortBy="volume"
        sortOrder="asc"
        onSort={onSort}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /最新价/ }))

    expect(onSort).toHaveBeenCalledWith('current_price')
  })

  it('renders mobile card list', () => {
    render(
      <QuoteTable
        products={[makeProduct(1), makeProduct(2)]}
        sortBy="volume"
        sortOrder="asc"
        onSort={vi.fn()}
      />,
    )

    // 移动端卡片和桌面端表格同时存在（由 CSS 控制显示/隐藏）
    expect(screen.getByRole('link', { name: /品种1/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /品种2/ })).toBeInTheDocument()
  })

  it('renders detail links for each product', () => {
    render(
      <QuoteTable
        products={[makeProduct(1)]}
        sortBy="change_percent"
        sortOrder="desc"
        onSort={vi.fn()}
      />,
    )

    const link = screen.getByRole('link', { name: /详情/ })
    expect(link).toHaveAttribute('href', '/products/1')
  })

  it('renders limit badges when price is near limit', () => {
    const product = makeProduct(1, {
      current_price: 100,
      limit_up: 100,
      limit_down: 90,
    })

    render(
      <QuoteTable
        products={[product]}
        sortBy="change_percent"
        sortOrder="desc"
        onSort={vi.fn()}
      />,
    )

    const table = screen.getByRole('table')
    expect(within(table).getByText('涨停')).toBeInTheDocument()
  })
})
