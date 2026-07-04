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
    selectedSource: 'main',
    selectedPeriod: '1d',
    displayedSource: 'main',
    displayedPeriod: '1d',
    isLoading: false,
    isContractsLoading: false,
    notice: null,
    viewportResetKey: 'RB:main:1d:none',
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
  it('renders main contract kline by default', () => {
    renderKlineSection()
    expect(screen.getByTestId('kline-chart')).toHaveTextContent('RB:1')
  })
})
