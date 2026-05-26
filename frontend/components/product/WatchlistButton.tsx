'use client'

import { Bookmark, BookmarkCheck } from 'lucide-react'
import { toast } from 'sonner'
import { api } from '@/lib/api'
import { captureMessage } from '@/lib/sentry-lite'

interface WatchlistButtonProps {
  varietyId: number
  isInWatchlist: boolean
  watchlistId: number | null
  onToggle: (inList: boolean, id: number | null) => void
}

export default function WatchlistButton({
  varietyId,
  isInWatchlist,
  watchlistId,
  onToggle,
}: WatchlistButtonProps) {
  const handleClick = async () => {
    try {
      if (isInWatchlist && watchlistId != null) {
        await api.deleteWatchlist(watchlistId)
        onToggle(false, null)
        toast.success('已取消自选')
        captureMessage(`取消自选: 品种#${varietyId}`, 'info')
      } else {
        const item = await api.createWatchlist(varietyId)
        onToggle(true, item.id)
        toast.success('已加入自选')
        captureMessage(`加入自选: 品种#${varietyId}`, 'info')
      }
    } catch (err) {
      toast.error('自选操作失败')
      captureMessage(`自选操作失败: 品种#${varietyId}, ${err instanceof Error ? err.message : '未知错误'}`, 'error')
    }
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 text-xs font-medium transition ${
        isInWatchlist
          ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
          : 'border-slate-700 bg-black/20 text-slate-400 hover:border-slate-500 hover:text-slate-200'
      }`}
    >
      {isInWatchlist ? <BookmarkCheck size={13} /> : <Bookmark size={13} />}
      {isInWatchlist ? '已自选' : '加入自选'}
    </button>
  )
}
