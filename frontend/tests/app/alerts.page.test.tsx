import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type React from 'react'
import { SWRConfig } from 'swr'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AlertsPage from '@/app/alerts/page'
import { api, type AlertEvent } from '@/lib/api'

const mockUseAuth = vi.fn()

vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => mockUseAuth(),
}))

vi.mock('@/components/auth/LoginRequired', () => ({
  default: () => <div data-testid="login-required">请登录</div>,
}))

vi.mock('@/components/layout/AppShell', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

function renderPage() {
  return render(
    <SWRConfig value={{ provider: () => new Map(), dedupingInterval: 0 }}>
      <AlertsPage />
    </SWRConfig>,
  )
}

const event: AlertEvent = {
  id: 1,
  category: 'news',
  severity: 'critical',
  title: 'FOMC 决议公布',
  summary: '市场波动加剧',
  source_type: 'news_article',
  source_id: 12,
  source_url: 'https://example.com/news',
  related_variety_id: null,
  related_variety_symbol: null,
  related_variety_name: null,
  user_id: null,
  target_scope: 'broadcast',
  triggered_at: '2026-07-04T10:00:00Z',
  created_at: '2026-07-04T10:00:00Z',
  read_at: null,
  dismissed_at: null,
}

describe('AlertsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseAuth.mockReturnValue({ isAuthenticated: true, isLoading: false })
    vi.spyOn(api, 'getAlertSummary').mockResolvedValue({ unread_count: 1, news_count: 1, market_count: 0 })
    vi.spyOn(api, 'getAlertEvents').mockResolvedValue([event])
    vi.spyOn(api, 'getVarieties').mockResolvedValue({ items: [], total: 0 })
    vi.spyOn(api, 'getPriceAlerts').mockResolvedValue([])
    vi.spyOn(api, 'markAlertEventRead').mockResolvedValue({ ...event, read_at: '2026-07-04T10:01:00Z' })
    vi.spyOn(api, 'dismissAlertEvent').mockResolvedValue({ ...event, read_at: '2026-07-04T10:01:00Z', dismissed_at: '2026-07-04T10:02:00Z' })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows LoginRequired for unauthenticated users', () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false, isLoading: false })

    renderPage()

    expect(screen.getByTestId('login-required')).toBeInTheDocument()
  })

  it('renders empty state', async () => {
    vi.spyOn(api, 'getAlertEvents').mockResolvedValue([])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('暂无预警事件')).toBeInTheDocument()
    })
  })

  it('renders alert event cards', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('FOMC 决议公布')).toBeInTheDocument()
    })
    expect(screen.getByText('紧急')).toBeInTheDocument()
    expect(screen.getByText('市场波动加剧')).toBeInTheDocument()
  })

  it('filters by tab', async () => {
    renderPage()

    fireEvent.click(screen.getByRole('button', { name: '新闻预警' }))

    await waitFor(() => {
      expect(api.getAlertEvents).toHaveBeenLastCalledWith({ category: 'news', limit: 80 })
    })
  })

  it('marks event as read and dismisses event', async () => {
    renderPage()

    await waitFor(() => {
      expect(screen.getByText('FOMC 决议公布')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: '标记已读' }))
    await waitFor(() => {
      expect(api.markAlertEventRead).toHaveBeenCalledWith(1)
    })

    fireEvent.click(screen.getByRole('button', { name: '忽略' }))
    await waitFor(() => {
      expect(api.dismissAlertEvent).toHaveBeenCalledWith(1)
    })
  })
})
