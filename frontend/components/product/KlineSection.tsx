import { RefreshCw } from 'lucide-react'
import KlineChart from '@/components/KlineChart'
import { FutContract, KlineData } from '@/lib/api'
import { KLINE_PERIODS, KLINE_SOURCES, KlinePeriod, KlineSource } from '@/lib/kline'

interface KlineSectionProps {
  data: KlineData[]
  symbol: string
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
    <div className="min-h-[420px] space-y-3">
      <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          {KLINE_SOURCES.map((source) => {
            const isSelected = selectedSource === source.value
            const isSingleUnavailable = source.value === 'single' && !isContractsLoading && contracts.length === 0
            return (
              <button
                key={source.value}
                type="button"
                disabled={isLoading || isSingleUnavailable}
                onClick={() => onSelectSource(source.value)}
                className={`h-8 rounded border px-3 text-sm transition ${
                  isSelected
                    ? 'border-amber-500 bg-amber-500/15 text-amber-200'
                    : 'border-slate-700 bg-black/20 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                } disabled:cursor-not-allowed disabled:opacity-60`}
                title={getSourceTitle(source.value)}
              >
                {source.label}
              </button>
            )
          })}

          {selectedSource === 'single' && (
            <select
              value={selectedContractId ?? ''}
              disabled={isLoading || isContractsLoading || contracts.length === 0}
              onChange={(event) => onSelectContract(event.target.value ? Number(event.target.value) : null)}
              className="h-8 min-w-[180px] rounded border border-slate-700 bg-surface px-2 text-sm text-slate-200 outline-none transition focus:border-amber-500 disabled:cursor-wait disabled:opacity-60"
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

          <div className="mx-1 hidden h-5 w-px bg-slate-700 sm:block" />
          {KLINE_PERIODS.map((period) => {
            const isSelected = selectedPeriod === period.value
            return (
              <button
                key={period.value}
                type="button"
                disabled={isLoading}
                onClick={() => onSelectPeriod(period.value)}
                className={`h-8 rounded border px-3 text-sm transition ${
                  isSelected
                    ? 'border-red-500 bg-red-500/15 text-red-200'
                    : 'border-slate-700 bg-black/20 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                } disabled:cursor-wait disabled:opacity-60`}
              >
                {period.label}
              </button>
            )
          })}
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          {(isLoading || isContractsLoading) && <RefreshCw size={13} className="animate-spin text-slate-400" />}
          <span>
            {KLINE_SOURCES.find((source) => source.value === displayedSource)?.label ?? displayedSource}
            {displayedSource === 'single' && selectedContract ? ` · ${formatContractLabel(selectedContract)}` : ''}
            {' · '}
            {KLINE_PERIODS.find((period) => period.value === displayedPeriod)?.label ?? displayedPeriod}
          </span>
        </div>
      </div>

      {notice && (
        <div className="mb-3 rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
          {notice}
        </div>
      )}

      <KlineChart
        data={data}
        symbol={symbol}
        supportLevels={supportLevels}
        resistanceLevels={resistanceLevels}
        onAddSupport={onAddSupport}
        onAddResistance={onAddResistance}
        onRemoveSupport={onRemoveSupport}
        onRemoveResistance={onRemoveResistance}
      />
    </div>
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
