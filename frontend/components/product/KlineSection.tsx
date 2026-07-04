import { RefreshCw } from 'lucide-react'
import KlineChart from '@/components/KlineChart'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import { FutContract, KlineData } from '@/lib/api'
import { KLINE_PERIODS, KLINE_SOURCES, KlinePeriod, KlineSource } from '@/lib/kline'

interface KlineSectionProps {
  data: KlineData[]
  symbol: string
  pricePrecision?: number
  contracts: FutContract[]
  selectedContractId: number | null
  selectedSource: KlineSource
  selectedPeriod: KlinePeriod
  displayedSource: KlineSource
  displayedPeriod: KlinePeriod
  isLoading: boolean
  isContractsLoading: boolean
  notice: string | null
  viewportResetKey: string
  supportLevels: number[]
  resistanceLevels: number[]
  onSelectContract: (contractId: number | null) => void
  onSelectSource: (source: KlineSource) => void
  onSelectPeriod: (period: KlinePeriod) => void
  onAddSupport: (price: number) => void
  onAddResistance: (price: number) => void
  onRemoveSupport: (price: number) => void
  onRemoveResistance: (price: number) => void
}

export default function KlineSection({
  data,
  symbol,
  pricePrecision = 2,
  contracts,
  selectedContractId,
  selectedSource,
  selectedPeriod,
  displayedSource,
  displayedPeriod,
  isLoading,
  isContractsLoading,
  notice,
  viewportResetKey,
  supportLevels,
  resistanceLevels,
  onSelectContract,
  onSelectSource,
  onSelectPeriod,
  onAddSupport,
  onAddResistance,
  onRemoveSupport,
  onRemoveResistance,
}: KlineSectionProps) {
  const selectedContract = contracts.find((contract) => contract.id === selectedContractId) ?? null

  return (
    <Card className="min-h-[420px] space-y-3">
      <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {KLINE_SOURCES.map((source) => {
            const isSelected = selectedSource === source.value
            return (
              <Button
                key={source.value}
                type="button"
                size="sm"
                variant={isSelected ? 'secondary' : 'tertiary'}
                disabled={isLoading}
                onClick={() => onSelectSource(source.value)}
                title={getSourceTitle(source.value)}
              >
                {source.label}
              </Button>
            )
          })}
          <div className="mx-1 hidden h-5 w-px bg-gray-alpha-400 sm:block" />
          {KLINE_PERIODS.map((period) => {
            const isSelected = selectedPeriod === period.value
            return (
              <Button
                key={period.value}
                type="button"
                size="sm"
                variant={isSelected ? 'secondary' : 'tertiary'}
                disabled={isLoading}
                onClick={() => onSelectPeriod(period.value)}
              >
                {period.label}
              </Button>
            )
          })}
        </div>
        <div className="flex items-center gap-2 text-label-12 text-gray-700">
          {(isLoading || isContractsLoading) && <RefreshCw size={13} className="animate-spin text-gray-800" />}
          <span>
            {KLINE_SOURCES.find((source) => source.value === displayedSource)?.label ?? displayedSource}
            {' · '}
            {KLINE_PERIODS.find((period) => period.value === displayedPeriod)?.label ?? displayedPeriod}
          </span>
        </div>
      </div>

      {notice && (
        <div className="mb-3 rounded border border-amber-900/40 bg-amber-100 px-3 py-2 text-copy-14 text-amber-700">
          {notice}
        </div>
      )}

      <KlineChart
        data={data}
        symbol={symbol}
        pricePrecision={pricePrecision}
        resetKey={viewportResetKey}
        supportLevels={supportLevels}
        resistanceLevels={resistanceLevels}
        onAddSupport={onAddSupport}
        onAddResistance={onAddResistance}
        onRemoveSupport={onRemoveSupport}
        onRemoveResistance={onRemoveResistance}
      />
    </Card>
  )
}

function getSourceTitle(source: KlineSource) {
  if (source === 'continuous') return '按主力切换拼接的连续价格序列'
  return ''
}

function formatContractLabel(contract: FutContract) {
  const code = contract.ts_code || contract.symbol || `#${contract.id}`
  return contract.name ? `${code} ${contract.name}` : code
}
