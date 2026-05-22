'use client'

import { ReactNode } from 'react'
import { XCircle } from 'lucide-react'

interface LevelEditorProps {
  title: string
  icon: ReactNode
  tone: 'support' | 'resistance'
  inputValue: string
  levels: number[]
  isSaved: boolean
  onInputChange: (value: string) => void
  onAdd: () => void
  onRemove: (price: number) => void
}

export default function LevelEditor({
  title,
  icon,
  tone,
  inputValue,
  levels,
  isSaved,
  onInputChange,
  onAdd,
  onRemove,
}: LevelEditorProps) {
  const isSupport = tone === 'support'
  const colorClass = isSupport ? 'text-green-400' : 'text-red-400'
  const bgClass = isSupport ? 'bg-green-400/10 hover:bg-green-400/20' : 'bg-red-400/10 hover:bg-red-400/20'
  const borderFocus = isSupport ? 'focus:border-green-500' : 'focus:border-red-500'
  const inputId = `${tone}-level-input`

  return (
    <section className="rounded-lg border border-slate-800 bg-[#10161d] p-4">
      <h2 className="flex items-center gap-2 text-base font-semibold text-slate-200">
        {icon}
        {title}
      </h2>
      <div className="mt-1 text-xs text-slate-600">
        {isSaved ? '已同步到云端' : '正在同步标注...'}
      </div>
      <div className="mt-4 flex gap-2">
        <label htmlFor={inputId} className="sr-only">{title}</label>
        <input
          id={inputId}
          type="number"
          value={inputValue}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder="价格"
          className={`min-w-0 flex-1 rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white outline-none placeholder:text-slate-600 ${borderFocus}`}
        />
        <button
          type="button"
          onClick={onAdd}
          className={`rounded-lg px-3 py-2 text-sm font-medium transition ${colorClass} ${bgClass}`}
        >
          添加
        </button>
      </div>

      <div className="mt-3 flex min-h-8 flex-wrap gap-2">
        {levels.length === 0 ? (
          <span className="text-xs text-slate-600">暂无标记</span>
        ) : (
          levels.map((level) => (
            <button
              type="button"
              key={`${tone}-${level}`}
              onClick={() => onRemove(level)}
              className={`inline-flex items-center gap-1 rounded px-2 py-1 font-mono text-xs transition ${colorClass} ${bgClass}`}
              aria-label={`删除${title} ${level.toFixed(2)}`}
            >
              {level.toFixed(2)}
              <XCircle size={12} />
            </button>
          ))
        )}
      </div>
    </section>
  )
}
