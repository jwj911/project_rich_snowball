import { MessageSquare, PencilLine, Star, Target } from 'lucide-react'

interface WorkspaceSummaryProps {
  commentCount: number
  productCount: number
  annotationCount: number
  watchlistCount: number
}

export default function WorkspaceSummary({
  commentCount,
  productCount,
  annotationCount,
  watchlistCount,
}: WorkspaceSummaryProps) {
  return (
    <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Metric icon={MessageSquare} label="评论记录" value={String(commentCount)} />
      <Metric icon={Target} label="涉及品种" value={String(productCount)} />
      <Metric icon={PencilLine} label="本地标注" value={String(annotationCount)} />
      <Metric icon={Star} label="自选品种" value={String(watchlistCount)} muted />
    </section>
  )
}

function Metric({
  icon: Icon,
  label,
  value,
  muted = false,
}: {
  icon: typeof MessageSquare
  label: string
  value: string
  muted?: boolean
}) {
  return (
    <div className="rounded-lg border border-slate-800 bg-[#10161d] p-4">
      <div className="flex items-center gap-2 text-xs text-slate-500">
        <Icon size={15} />
        {label}
      </div>
      <div className={`mt-3 font-mono text-2xl font-semibold ${muted ? 'text-slate-500' : 'text-white'}`}>
        {value}
      </div>
    </div>
  )
}
