import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AnnotationContextMenu from '@/components/kline/AnnotationContextMenu'
import CrosshairTooltip from '@/components/kline/CrosshairTooltip'
import LevelChips from '@/components/kline/LevelChips'
import { CandlePoint } from '@/lib/klineChart'

const latestPoint: CandlePoint = {
  time: 1 as CandlePoint['time'],
  originalTime: '2026-05-16',
  open: 3600,
  high: 3660,
  low: 3580,
  close: 3650,
  volume: 1200,
  contractCode: 'RB2609.SHF',
}

describe('Kline chart pieces', () => {
  it('renders crosshair tooltip values and contract code', () => {
    render(<CrosshairTooltip quote={null} latestPoint={latestPoint} />)

    expect(screen.getByText('2026-05-16')).toBeInTheDocument()
    expect(screen.getByText('3,650.00')).toBeInTheDocument()
    expect(screen.getByText('1,200')).toBeInTheDocument()
    expect(screen.getByText('RB2609.SHF')).toBeInTheDocument()
  })

  it('emits annotation menu actions and respects disabled state', () => {
    const onAddSupport = vi.fn()
    const onAddResistance = vi.fn()
    const onClose = vi.fn()

    render(
      <AnnotationContextMenu
        menu={{ x: 12, y: 48, price: 3650.25 }}
        canAddSupport
        canAddResistance={false}
        onAddSupport={onAddSupport}
        onAddResistance={onAddResistance}
        onClose={onClose}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: '添加支撑位' }))
    fireEvent.click(screen.getByRole('button', { name: '取消' }))

    expect(screen.getByText('3650.25')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '添加阻力位' })).toBeDisabled()
    expect(onAddSupport).toHaveBeenCalled()
    expect(onAddResistance).not.toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('renders removable level chips', () => {
    const onRemove = vi.fn()

    render(<LevelChips title="支撑" levels={[3500, 3520.5]} tone="support" onRemove={onRemove} />)

    fireEvent.click(screen.getByRole('button', { name: '3500.00' }))

    expect(screen.getByText('支撑')).toBeInTheDocument()
    expect(onRemove).toHaveBeenCalledWith(3500)
  })
})
