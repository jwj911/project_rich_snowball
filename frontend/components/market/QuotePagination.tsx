import { ArrowLeft, ArrowRight } from 'lucide-react'

interface QuotePaginationProps {
  currentPage: number
  totalPages: number
  rangeStart: number
  rangeEnd: number
  totalItems: number
  onPrevious: () => void
  onNext: () => void
}

export default function QuotePagination({
  currentPage,
  totalPages,
  rangeStart,
  rangeEnd,
  totalItems,
  onPrevious,
  onNext,
}: QuotePaginationProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-800 bg-[#10161d] px-3 py-2 text-sm text-slate-400">
      <span>
        显示 {rangeStart}-{rangeEnd} / {totalItems}
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onPrevious}
          disabled={currentPage === 1}
          className="inline-flex h-8 items-center gap-1 rounded border border-slate-700 px-2 text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          <ArrowLeft size={14} />
          上一页
        </button>
        <span className="font-mono text-xs text-slate-500">
          {currentPage}/{totalPages}
        </span>
        <button
          type="button"
          onClick={onNext}
          disabled={currentPage === totalPages}
          className="inline-flex h-8 items-center gap-1 rounded border border-slate-700 px-2 text-slate-300 transition hover:border-slate-500 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
        >
          下一页
          <ArrowRight size={14} />
        </button>
      </div>
    </div>
  )
}
