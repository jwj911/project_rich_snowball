import { RefreshCw, Info } from 'lucide-react'
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
            const isSingleUnavailable = source.value === 'single' && !isContractsLoading && contracts.length === 0
            return (
              <Button
                key={source.value}
                type="button"
                size="sm"
                variant={isSelected ? 'secondary' : 'tertiary'}
                disabled={isLoading || isSingleUnavailable}
                onClick={() => onSelectSource(source.value)}
                title={getSourceTitle(source.value)}
              >
                {source.label}
              </Button>
            )
          })}

          {selectedSource === 'single' && (
            <select
              value={selectedContractId ?? ''}
              disabled={isLoading || isContractsLoading || contracts.length === 0}
              onChange={(event) => onSelectContract(event.target.value ? Number(event.target.value) : null)}
              className="h-8 min-w-[180px] rounded border border-gray-alpha-400 bg-background px-2 text-label-14 text-foreground outline-none transition hover:border-gray-alpha-500 focus:border-gray-alpha-500 focus:shadow-[0_0_0_2px_#000000,0_0_0_4px_#47a8ff] disabled:cursor-wait disabled:opacity-60"
              aria-label="选择具体合约"
            >
              {contracts.length === 0 ? (
                <option value="">暂无合约</option>
              ) : (
                contracts.map((contract) => (
                  <option key={contract.id} value={contract.id}>
                    {formatContractLabel(contract)}
                  </option>
                ))
              )}
            </select>
          )}

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
            {displayedSource === 'single' && selectedContract ? ` · ${formatContractLabel(selectedContract)}` : ''}
            {' · '}
            {KLINE_PERIODS.find((period) => period.value === displayedPeriod)?.label ?? displayedPeriod}
          </span>
        </div>
      </div>

      {selectedSource === 'single' && selectedContract && (
        <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 rounded border border-gray-alpha-400 bg-gray-100 px-3 py-2 text-label-12 text-gray-700">
          <span className="flex items-center gap-1.5">
            <Info size={12} className="text-gray-600" />
            <span className="font-mono text-foreground">{selectedContract.ts_code || selectedContract.symbol || `#${selectedContract.id}`}</span>
          </span>
          {selectedContract.exchange && (
            <span>交易所: {selectedContract.exchange}</span>
          )}
          {selectedContract.list_date && (
            <span>上市: {selectedContract.list_date.slice(0, 10)}</span>
          )}
          {selectedContract.delist_date && (
            <span>退市: {selectedContract.delist_date.slice(0, 10)}</span>
          )}
          <span className={selectedContract.is_active ? 'text-green-700' : 'text-gray-600'}>
            {selectedContract.is_active ? '交易中' : '已退市'}
          </span>
        </div>
      )}

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
  if (source === 'main') return '当前主力合约的独立 K 线'
  return '选择某一个具体合约查看 K 线'
}

function formatContractLabel(contract: FutContract) {
  const code = contract.ts_code || contract.symbol || `#${contract.id}`
  return contract.name ? `${code} ${contract.name}` : code
}
