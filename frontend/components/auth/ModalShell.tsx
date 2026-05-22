'use client'

import { ReactNode, useEffect } from 'react'
import { X } from 'lucide-react'

interface ModalShellProps {
  title: string
  children: ReactNode
  onClose: () => void
}

export default function ModalShell({ title, children, onClose }: ModalShellProps) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="w-full max-w-sm rounded-lg border border-slate-800 bg-[#10161d] p-5 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between gap-3">
          <h2 className="text-lg font-bold text-white">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-900 hover:text-white"
            aria-label="关闭"
          >
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
