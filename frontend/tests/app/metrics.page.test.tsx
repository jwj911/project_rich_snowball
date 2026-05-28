import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MetricsPage from '@/app/metrics/page'
import { api } from '@/lib/api'
import { makeDashboardOverview, makeDashboardActivity, makeDashboardCollection } from '@/tests/fixtures'

vi.mock('next/navigation', () => ({
  useRouter: () => ({
    replace: vi.fn(),
  }),
}))

const mockUseAuth = vi.fn()
vi.mock('@/components/auth/AuthProvider', () => ({
  useAuth: () => mockUseAuth(),
}))

describe('MetricsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseAuth.mockReturnValue({ isAuthenticated: true })
    vi.spyOn(api, 'getDashboardOverview').mockResolvedValue(makeDashboardOverview())
    vi.spyOn(api, 'getDashboardActivity').mockResolvedValue(makeDashboardActivity())
    vi.spyOn(api, 'getDashboardCollection').mockResolvedValue(makeDashboardCollection())
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('redirects unauthenticated users', async () => {
    mockUseAuth.mockReturnValue({ isAuthenticated: false })
    const replaceMock = vi.fn()
    const useRouterMock = vi.spyOn(await import('next/navigation'), 'useRouter')
    useRouterMock.mockReturnValue({ replace: replaceMock } as any)

    render(<MetricsPage />)

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith('/')
    })
  })

  it('shows loading state initially', () => {
    // Never resolve to keep loading state
    vi.spyOn(api, 'getDashboardOverview').mockImplementation(() => new Promise(() => {}))
    vi.spyOn(api, 'getDashboardActivity').mockImplementation(() => new Promise(() => {}))
    vi.spyOn(api, 'getDashboardCollection').mockImplementation(() => new Promise(() => {}))

    render(<MetricsPage />)
    expect(screen.getByText('加载中...')).toBeInTheDocument()
  })

  it('shows error state when API fails', async () => {
    vi.spyOn(api, 'getDashboardOverview').mockRejectedValue(new Error('服务暂不可用'))
    vi.spyOn(api, 'getDashboardActivity').mockRejectedValue(new Error('服务暂不可用'))
    vi.spyOn(api, 'getDashboardCollection').mockRejectedValue(new Error('服务暂不可用'))

    render(<MetricsPage />)

    await waitFor(() => {
      expect(screen.getByText('服务暂不可用')).toBeInTheDocument()
    })
  })

  it('renders dashboard data on success', async () => {
    render(<MetricsPage />)

    await waitFor(() => {
      expect(screen.getByText('运营指标面板')).toBeInTheDocument()
    })

    // Overview cards
    expect(screen.getByText('总用户数')).toBeInTheDocument()
    expect(screen.getByText('120')).toBeInTheDocument()
    expect(screen.getByText('评论总数')).toBeInTheDocument()
    expect(screen.getByText('450')).toBeInTheDocument()

    // Market cards
    expect(screen.getByText('品种总数')).toBeInTheDocument()
    expect(screen.getByText('56')).toBeInTheDocument()

    // Activity section
    expect(screen.getByText('最近 7 天趋势')).toBeInTheDocument()

    // Collection section
    expect(screen.getByText('数据采集健康度（最近 24h）')).toBeInTheDocument()
    expect(screen.getByText('采集任务')).toBeInTheDocument()
    expect(screen.getByText('48')).toBeInTheDocument()

    // Recent runs table
    expect(screen.getByText('daily_quotes')).toBeInTheDocument()
    expect(screen.getByText('variety_info')).toBeInTheDocument()
  })

  it('renders empty collection gracefully', async () => {
    vi.spyOn(api, 'getDashboardCollection').mockResolvedValue({
      ...makeDashboardCollection(),
      recent_runs: [],
    })

    render(<MetricsPage />)

    await waitFor(() => {
      expect(screen.getByText('数据采集健康度（最近 24h）')).toBeInTheDocument()
    })

    // Table should not appear when no recent runs
    expect(screen.queryByText('daily_quotes')).not.toBeInTheDocument()
  })
})
