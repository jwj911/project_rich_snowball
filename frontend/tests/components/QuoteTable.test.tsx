import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
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
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders one page at a time and paginates table rows', () => {
    const products = Array.from({ length: 5 }, (_, index) => makeProduct(index + 1))

    render(
      <QuoteTable
        products={products}
        sortBy="change_percent"
        sortOrder="desc"
        onSort={vi.fn()}
        pageSize={2}
      />,
    )

    const table = screen.getByRole('table')
    expect(within(table).getByText('品种1')).toBeInTheDocument()
    expect(within(table).getByText('品种2')).toBeInTheDocument()
    expect(within(table).queryByText('品种3')).not.toBeInTheDocument()
    expect(screen.getByText('显示 1-2 / 5')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /下一页/ }))

    expect(within(table).queryByText('品种1')).not.toBeInTheDocument()
    expect(within(table).getByText('品种3')).toBeInTheDocument()
    expect(within(table).getByText('品种4')).toBeInTheDocument()
    expect(screen.getByText('显示 3-4 / 5')).toBeInTheDocument()
  })

  it('emits sort changes and marks the active column with aria-sort', () => {
    const onSort = vi.fn()

    render(
      <QuoteTable
        products={[makeProduct(1), makeProduct(2)]}
        sortBy="volume"
        sortOrder="asc"
        onSort={onSort}
        pageSize={10}
      />,
    )

    expect(screen.getByRole('columnheader', { name: /成交量/ })).toHaveAttribute('aria-sort', 'ascending')
    expect(screen.getByRole('columnheader', { name: /涨跌幅/ })).toHaveAttribute('aria-sort', 'none')

    fireEvent.click(screen.getByRole('button', { name: /最新价/ }))

    expect(onSort).toHaveBeenCalledWith('current_price')
  })

  it('resets to the first page when the product list changes', () => {
    const { rerender } = render(
      <QuoteTable
        products={[makeProduct(1), makeProduct(2), makeProduct(3)]}
        sortBy="change_percent"
        sortOrder="desc"
        onSort={vi.fn()}
        pageSize={1}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: /下一页/ }))
    expect(screen.getByText('显示 2-2 / 3')).toBeInTheDocument()

    rerender(
      <QuoteTable
        products={[makeProduct(4), makeProduct(5)]}
        sortBy="change_percent"
        sortOrder="desc"
        onSort={vi.fn()}
        pageSize={1}
      />,
    )

    expect(screen.getByText('显示 1-1 / 2')).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByText('品种4')).toBeInTheDocument()
  })

  it('delegates pagination when current page and total count are controlled', () => {
    const onPageChange = vi.fn()

    render(
      <QuoteTable
        products={[makeProduct(51), makeProduct(52)]}
        sortBy="change_percent"
        sortOrder="desc"
        onSort={vi.fn()}
        pageSize={50}
        currentPage={2}
        totalItems={120}
        onPageChange={onPageChange}
      />,
    )

    expect(screen.getByText(/显示 51-52 \/ 120/)).toBeInTheDocument()
    expect(within(screen.getByRole('table')).getByText('品种51')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /上一页/ }))
    fireEvent.click(screen.getByRole('button', { name: /下一页/ }))

    expect(onPageChange).toHaveBeenNthCalledWith(1, 1)
    expect(onPageChange).toHaveBeenNthCalledWith(2, 3)
  })

  it('mounts only the mobile card list on small screens', () => {
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false,
      media: '(min-width: 768px)',
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))

    render(
      <QuoteTable
        products={[makeProduct(1), makeProduct(2)]}
        sortBy="volume"
        sortOrder="asc"
        onSort={vi.fn()}
        pageSize={10}
      />,
    )

    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /品种1/ })).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: /成交量/ })).not.toBeInTheDocument()
  })
})
