interface LevelChipsProps {
  title: string
  levels: number[]
  tone: 'support' | 'resistance'
  onRemove?: (price: number) => void
}

export default function LevelChips({ title, levels, tone, onRemove }: LevelChipsProps) {
  if (levels.length === 0) return null

  const colorClass = tone === 'support'
    ? 'border-green-400/30 bg-green-400/10 text-green-300'
    : 'border-red-400/30 bg-red-400/10 text-red-300'

  return (
    <div>
      <div className="mb-1 text-slate-500">{title}</div>
      <div className="flex flex-wrap gap-1">
        {levels.map((level) => (
          <button
            key={`${tone}-${level}`}
            type="button"
            onClick={() => onRemove?.(level)}
            className={`rounded border px-1.5 py-1 font-mono transition hover:bg-slate-700/40 ${colorClass}`}
            title="点击删除"
          >
            {level.toFixed(2)}
          </button>
        ))}
      </div>
    </div>
  )
}
