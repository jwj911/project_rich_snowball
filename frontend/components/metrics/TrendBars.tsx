'use client'

interface TrendBarsProps {
  data: { date: string; count: number }[]
  label: string
  colorClass?: string
}

export default function TrendBars({ data, label, colorClass = 'bg-red-500' }: TrendBarsProps) {
  const max = Math.max(...data.map((d) => d.count), 1)

  return (
    <div className="rounded-xl border border-slate-800 bg-surface p-5">
      <h3 className="text-sm font-semibold text-white">{label}</h3>
      <div className="mt-4 flex items-end gap-2">
        {data.map((item) => {
          const heightPercent = (item.count / max) * 100
          return (
            <div key={item.date} className="flex flex-1 flex-col items-center gap-1.5">
              <div className="flex w-full flex-1 items-end">
                <div
                  className={`w-full rounded-t ${colorClass} opacity-80 transition-all`}
                  style={{ height: `${Math.max(heightPercent, 4)}%`, minHeight: 4 }}
                  title={`${item.date}: ${item.count}`}
                />
              </div>
              <span className="text-[10px] text-slate-500">
                {item.date.slice(5)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
