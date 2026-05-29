import { AnnotationMenu } from '@/lib/klineChart'
import { formatPrice } from '@/lib/format'

interface AnnotationContextMenuProps {
  menu: AnnotationMenu
  pricePrecision?: number
  canAddSupport: boolean
  canAddResistance: boolean
  onAddSupport: () => void
  onAddResistance: () => void
  onClose: () => void
}

export default function AnnotationContextMenu({
  menu,
  pricePrecision,
  canAddSupport,
  canAddResistance,
  onAddSupport,
  onAddResistance,
  onClose,
}: AnnotationContextMenuProps) {
  return (
    <div
      className="absolute z-20 w-40 rounded-lg border border-border bg-surface-elevated p-2 text-xs shadow-xl"
      style={{ left: menu.x, top: menu.y }}
      onClick={(event) => event.stopPropagation()}
    >
      <div className="mb-2 border-b border-border pb-2 font-mono text-slate-200">
        {formatPrice(menu.price, pricePrecision)}
      </div>
      <button
        type="button"
        onClick={onAddSupport}
        disabled={!canAddSupport}
        className="flex w-full items-center justify-between rounded px-2 py-2 text-left text-green-300 transition hover:bg-green-400/10 disabled:cursor-not-allowed disabled:opacity-40"
      >
        添加支撑位
        <span className="h-2 w-2 rounded-full bg-green-400" />
      </button>
      <button
        type="button"
        onClick={onAddResistance}
        disabled={!canAddResistance}
        className="mt-1 flex w-full items-center justify-between rounded px-2 py-2 text-left text-red-300 transition hover:bg-red-400/10 disabled:cursor-not-allowed disabled:opacity-40"
      >
        添加阻力位
        <span className="h-2 w-2 rounded-full bg-red-400" />
      </button>
      <button
        type="button"
        onClick={onClose}
        className="mt-1 w-full rounded px-2 py-2 text-left text-slate-400 transition hover:bg-slate-700/40 hover:text-slate-200"
      >
        取消
      </button>
    </div>
  )
}
