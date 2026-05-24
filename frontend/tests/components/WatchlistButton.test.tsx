import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import WatchlistButton from '@/components/product/WatchlistButton'
import { api } from '@/lib/api'
import { toast } from 'sonner'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/api', () => ({
  api: {
    createWatchlist: vi.fn(),
    deleteWatchlist: vi.fn(),
  },
}))

describe('WatchlistButton', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders "加入自选" when not in watchlist', () => {
    render(
      <WatchlistButton
        varietyId={1}
        isInWatchlist={false}
        watchlistId={null}
        onToggle={() => {}}
      />,
    )
    expect(screen.getByRole('button', { name: '加入自选' })).toBeInTheDocument()
  })

  it('renders "已自选" when in watchlist', () => {
    render(
      <WatchlistButton
        varietyId={1}
        isInWatchlist
        watchlistId={42}
        onToggle={() => {}}
      />,
    )
    expect(screen.getByRole('button', { name: '已自选' })).toBeInTheDocument()
  })

  it('calls createWatchlist and shows success when adding', async () => {
    const onToggle = vi.fn()
    vi.mocked(api.createWatchlist).mockResolvedValue({
      id: 42,
      user_id: 1,
      variety_id: 1,
      variety_symbol: 'RB',
      variety_name: '螺纹钢',
      notes: null,
      is_notified: false,
      created_at: '',
    })

    render(
      <WatchlistButton
        varietyId={1}
        isInWatchlist={false}
        watchlistId={null}
        onToggle={onToggle}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '加入自选' }))

    await waitFor(() => {
      expect(api.createWatchlist).toHaveBeenCalledWith(1)
      expect(onToggle).toHaveBeenCalledWith(true, 42)
      expect(toast.success).toHaveBeenCalledWith('已加入自选')
    })
  })

  it('calls deleteWatchlist and shows success when removing', async () => {
    const onToggle = vi.fn()
    vi.mocked(api.deleteWatchlist).mockResolvedValue(undefined)

    render(
      <WatchlistButton
        varietyId={1}
        isInWatchlist
        watchlistId={42}
        onToggle={onToggle}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '已自选' }))

    await waitFor(() => {
      expect(api.deleteWatchlist).toHaveBeenCalledWith(42)
      expect(onToggle).toHaveBeenCalledWith(false, null)
      expect(toast.success).toHaveBeenCalledWith('已取消自选')
    })
  })

  it('shows error toast on API failure', async () => {
    vi.mocked(api.createWatchlist).mockRejectedValue(new Error('network'))

    render(
      <WatchlistButton
        varietyId={1}
        isInWatchlist={false}
        watchlistId={null}
        onToggle={() => {}}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '加入自选' }))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('自选操作失败')
    })
  })
})
