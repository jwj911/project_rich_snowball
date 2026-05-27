import Link from 'next/link'
import EmptyState from '@/components/ui/EmptyState'
import { formatDateTime, formatNumber } from '@/lib/format'
import { PencilLine } from 'lucide-react'

export interface WorkspaceAnnotation {
  productId: number
  productName: string
  symbol: string
  supportLevels: number[]
  resistanceLevels: number[]
  updatedAt?: string
}

export default function MyAnnotationsPanel({ annotations }: { annotations: WorkspaceAnnotation[] }) {
  return (
    <section className="rounded-lg border border-slate-800 bg-surface p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-white">我的标注</h2>
          <p className="mt-1 text-xs text-slate-500">同步自云端保存的支撑位和阻力位。</p>
        </div>
        <span className="rounded border border-slate-700 px-2 py-1 text-xs text-slate-500">云端</span>
      </div>

      {annotations.length === 0 ? (
        <EmptyState
          icon={PencilLine}
          title="暂无标注"
          description="进入品种详情页添加支撑位或阻力位后，这里会聚合展示。"
          className="mt-4 bg-black/20"
        />
      ) : (
        <div className="mt-4 space-y-3">
          {annotations.map((annotation) => (
            <Link
              key={annotation.productId}
              href={`/products/${annotation.productId}`}
              className="block rounded-lg border border-slate-800 bg-black/20 p-3 transition hover:border-red-800/80 hover:bg-[#121b24]"
            >
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div className="font-medium text-white">{annotation.productName}</div>
                  <div className="mt-1 font-mono text-xs text-slate-500">{annotation.symbol}</div>
                </div>
                <div className="font-mono text-xs text-slate-600">
                  {annotation.updatedAt ? formatDateTime(annotation.updatedAt) : '--'}
                </div>
              </div>
              <LevelRow label="支撑" values={annotation.supportLevels} tone="support" />
              <LevelRow label="阻力" values={annotation.resistanceLevels} tone="resistance" />
            </Link>
          ))}
        </div>
      )}
    </section>
  )
}

function LevelRow({
  label,
  values,
  tone,
}: {
  label: string
  values: number[]
  tone: 'support' | 'resistance'
}) {
  const toneClass = tone === 'support' ? 'text-green-300 bg-green-400/10' : 'text-red-300 bg-red-400/10'

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <span className="w-9 shrink-0 text-xs text-slate-500">{label}</span>
      {values.length === 0 ? (
        <span className="text-xs text-slate-600">未设置</span>
      ) : (
        values.map((value) => (
          <span key={`${label}-${value}`} className={`rounded px-2 py-1 font-mono text-xs ${toneClass}`}>
            {formatNumber(value)}
          </span>
        ))
      )}
    </div>
  )
}
