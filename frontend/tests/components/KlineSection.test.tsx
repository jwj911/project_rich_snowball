import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import KlineSection from '@/components/product/KlineSection'
import { FutContract } from '@/lib/api'

vi.mock('@/components/KlineChart', () => ({
  default: ({ symbol, data }: { symbol: string; data: unknown[] }) => (
    <div data-testid="kline-chart">
      {symbol}:{data.length}
    </div>
  ),
}))

const contracts: FutContract[] = [
  {
    id: 12,
    ts_code: 'RB2609.SHF',
    symbol: 'RB2609',
    name: '螺纹钢2609',
    fut_code: 'RB',
    exchange: 'SHFE',
    list_date: null,
    delist_date: null,
    contract_type: null,
    is_active: true,
  },
  {
    id: 13,
    ts_code: 'RB2610.SHF',
    symbol: 'RB2610',
    name: null,
    fut_code: 'RB',
    exchange: 'SHFE',
    list_date: null,
    delist_date: null,
    contract_type: null,
    is_active: true,
  },
]

function renderKlineSection(overrides: Partial<React.ComponentProps<typeof KlineSection>> = {}) {
  const props: React.ComponentProps<typeof KlineSection> = {
    data: [{ time: '2026-05-01', open: 1, high: 2, low: 1, close: 2, volume: 100 }],
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
