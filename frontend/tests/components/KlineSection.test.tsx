import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import KlineSection from '@/components/product/KlineSection'
import { makeFutContract, makeKline } from '@/tests/fixtures'

vi.mock('@/components/KlineChart', () => ({
  default: ({ symbol, data }: { symbol: string; data: unknown[] }) => (
    <div data-testid="kline-chart">
      {symbol}:{data.length}
    </div>
  ),
}))

const contracts = [
  makeFutContract(),
  makeFutContract({ id: 13, ts_code: 'RB2610.SHF', symbol: 'RB2610', name: null }),
]

function renderKlineSection(overrides: Partial<React.ComponentProps<typeof KlineSection>> = {}) {
  const props: React.ComponentProps<typeof KlineSection> = {
    data: [makeKline()],
    symbol: 'RB',
    contracts,
    selectedContractId: 12,
    selectedSource: 'continuous',
    selectedPeriod: '1d',
    displayedSource: 'continuous',
    displayedPeriod: '1d',
    isLoading: false,
    isContractsLoading: false,
    notice: null,
    viewportResetKey: 'RB:continuous:1d:none',
    supportLevels: [],
    resistanceLevels: [],
    onSelectContract: vi.fn(),
    onSelectSource: vi.fn(),
    onSelectPeriod: vi.fn(),
    onAddSupport: vi.fn(),
    onAddResistance: vi.fn(),
    onRemoveSupport: vi.fn(),
    onRemoveResistance: vi.fn(),
    ...overrides,
  }

  render(<KlineSection {...props} />)
  return props
}

describe('KlineSection', () => {
  it('switches between continuous, main, and single contract sources', () => {
    const onSelectSource = vi.fn()

    renderKlineSection({ onSelectSource })

    fireEvent.click(screen.getByRole('button', { name: '主力合约' }))
    fireEvent.click(screen.getByRole('button', { name: '具体合约' }))

    expect(onSelectSource).toHaveBeenNthCalledWith(1, 'main')
    expect(onSelectSource).toHaveBeenNthCalledWith(2, 'single')
    expect(screen.getByTestId('kline-chart')).toHaveTextContent('RB:1')
  })

  it('shows a concrete contract selector and emits selected contract id', () => {
    const onSelectContract = vi.fn()

    renderKlineSection({
      selectedSource: 'single',
      displayedSource: 'single',
      onSelectContract,
    })

    const selector = screen.getByRole('combobox', { name: '选择具体合约' })
    expect(within(selector).getByRole('option', { name: 'RB2609.SHF 螺纹钢2609' })).toBeInTheDocument()
    expect(within(selector).getByRole('option', { name: 'RB2610.SHF' })).toBeInTheDocument()

    fireEvent.change(selector, { target: { value: '13' } })

    expect(onSelectContract).toHaveBeenCalledWith(13)
    expect(screen.getByText('具体合约 · RB2609.SHF 螺纹钢2609 · 日线')).toBeInTheDocument()
  })

  it('disables the single-contract entry when no contracts are available', () => {
    renderKlineSection({
      contracts: [],
      selectedContractId: null,
    })

    expect(screen.getByRole('button', { name: '具体合约' })).toBeDisabled()
  })
})
