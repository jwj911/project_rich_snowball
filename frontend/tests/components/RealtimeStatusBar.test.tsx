import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import RealtimeStatusBar from '@/components/product/RealtimeStatusBar'

describe('RealtimeStatusBar', () => {
  it('shows SSE realtime status and update time', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-05-21T12:00:30.000Z'))

    render(
      <RealtimeStatusBar
        source="sse"
        loading={false}
        error={null}
        updatedAt="2026-05-21T12:00:00.000Z"
        usingLiveQuote
      />,
    )

    expect(screen.getByText('实时行情：SSE 推送')).toBeInTheDocument()
    expect(screen.getByText('30 秒前')).toBeInTheDocument()

    vi.useRealTimers()
  })

  it('shows polling fallback and error details', () => {
    render(
      <RealtimeStatusBar
        source="polling"
        loading
        error="SSE 连接失败，已降级为轮询并会自动重试"
        updatedAt={null}
        usingLiveQuote={false}
      />,
    )

    expect(screen.getByText('实时行情：轮询降级')).toBeInTheDocument()
    expect(screen.getByText('连接中')).toBeInTheDocument()
    expect(screen.getByText('SSE 连接失败，已降级为轮询并会自动重试')).toBeInTheDocument()
  })
})
