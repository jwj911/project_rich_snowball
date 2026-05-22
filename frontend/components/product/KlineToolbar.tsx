'use client'

import { RefreshCw } from 'lucide-react'

export type KlinePeriod = '1m' | '5m' | '15m' | '30m' | '1h' | '1d' | '1w'
export type KlineSource = 'continuous' | 'main' | 'single'

const KLINE_SOURCES: Array<{ value: KlineSource; label: string }> = [
  { value: 'continuous', label: '连续K线' },
  { value: 'main', label: '主力合约' },
  { value: 'single', label: '单合约' },
]

const KLINE_PERIODS: Array<{ value: KlinePeriod; label: string }> = [
  { value: '1m', label: '1分' },
  { value: '5m', label: '5分' },
  { value: '15m', label: '15分' },
  { value: '30m', label: '30分' },
  { value: '1h', label: '1小时' },
  { value: '1d', label: '日线' },
  { value: '1w', label: '周线' },
]

interface KlineToolbarProps {
  selectedSource: KlineSource
  selectedPeriod: KlinePeriod
  displayedSource: KlineSource
  displayedPeriod: KlinePeriod
  isLoading: boolean
  onSourceChange: (source: KlineSource) => void
  onPeriodChange: (period: KlinePeriod) => void
}

export default function KlineToolbar({
  selectedSource,
  selectedPeriod,
  displayedSource,
  displayedPeriod,
  isLoading,
  onSourceChange,
  onPeriodChange,
}: KlineToolbarProps) {
  return (
    <div className="mb-3 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex flex-wrap items-center gap-2">
        {KLINE_SOURCES.map((source) => {
          const isSelected = selectedSource === source.value
          return (
            <button
              key={source.value}
              type="button"
              disabled={isLoading}
              onClick={() => onSourceChange(source.value)}
              className={`h-8 rounded border px-3 text-sm transition ${
                isSelected
                  ? 'border-amber-500 bg-amber-500/15 text-amber-200'
                  : 'border-slate-700 bg-black/20 text-slate-400 hover:border-slate-500 hover:text-slate-200'
              } disabled:cursor-wait disabled:opacity-60`}
              title={
                source.value === 'continuous'
                  ? '按主力合约切换拼接的连续价格序列'
                  : source.value === 'main'
                    ? '当前主力合约的独立 K 线'
                    : '单品种标准 K 线'
              }
            >
              {source.label}
            </button>
          )
        })}
        <div className="mx-1 hidden h-5 w-px bg-slate-700 sm:block" />
        {KLINE_PERIODS.map((period) => {
          const isSelected = selectedPeriod === period.value
          return (
            <button
              key={period.value}
              type="button"
              disabled={isLoading}
              onClick={() => onPeriodChange(period.value)}
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
        {isLoading && <RefreshCw size={13} className="animate-spin text-slate-400" />}
        <span>
          {KLINE_SOURCES.find((s) => s.value === displayedSource)?.label ?? displayedSource}
          ·
          {KLINE_PERIODS.find((p) => p.value === displayedPeriod)?.label ?? displayedPeriod}
        </span>
      </div>
    </div>
  )
}
