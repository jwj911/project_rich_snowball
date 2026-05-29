import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import MarketSessionBadge from '@/components/market/MarketSessionBadge'

vi.mock('@/lib/swr-hooks', () => ({
  useMarketStatus: vi.fn(),
}))

import { useMarketStatus } from '@/lib/swr-hooks'

const mockedUseMarketStatus = vi.mocked(useMarketStatus)

describe('MarketSessionBadge', () => {
  it('renders day session when backend returns day', () => {
    mockedUseMarketStatus.mockReturnValue({
      data: { current_session: 'day', is_trading_day: true, remark: null },
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
      isValidating: false,
    } as unknown as ReturnType<typeof useMarketStatus>)

    render(<MarketSessionBadge />)
    expect(screen.getByText('日盘交易中')).toBeInTheDocument()
  })

  it('renders night session when backend returns night', () => {
    mockedUseMarketStatus.mockReturnValue({
      data: { current_session: 'night', is_trading_day: true, remark: null },
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
      isValidating: false,
    } as unknown as ReturnType<typeof useMarketStatus>)

    render(<MarketSessionBadge />)
    expect(screen.getByText('夜盘交易中')).toBeInTheDocument()
  })

  it('renders closed session when backend returns closed', () => {
    mockedUseMarketStatus.mockReturnValue({
      data: { current_session: 'closed', is_trading_day: false, remark: null },
      error: undefined,
      isLoading: false,
      mutate: vi.fn(),
      isValidating: false,
    } as unknown as ReturnType<typeof useMarketStatus>)

    render(<MarketSessionBadge />)
    expect(screen.getByText('休市中')).toBeInTheDocument()
  })

  it('falls back to local rule when backend is unavailable', () => {
    mockedUseMarketStatus.mockReturnValue({
      data: undefined,
      error: new Error('network error'),
      isLoading: false,
      mutate: vi.fn(),
      isValidating: false,
    } as unknown as ReturnType<typeof useMarketStatus>)

    const { container } = render(<MarketSessionBadge />)
    // 应渲染 fallback 状态（day/night/closed 之一），不白屏
    expect(container.textContent).toMatch(/日盘交易中|夜盘交易中|休市中/)
  })
})
