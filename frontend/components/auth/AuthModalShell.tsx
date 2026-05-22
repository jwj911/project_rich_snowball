'use client'

import { ReactNode, useEffect, useId, useRef } from 'react'
import { X } from 'lucide-react'

interface AuthModalShellProps {
  title: string
  children: ReactNode
  onClose: () => void
}

export default function AuthModalShell({
  title,
  children,
  onClose,
}: AuthModalShellProps) {
  const titleId = useId()
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const dialog = dialogRef.current
    const preferredFocus = dialog?.querySelector<HTMLElement>('[data-autofocus]')
    const focusable = getFocusableElements(dialog)
    const firstFocusable = preferredFocus ?? focusable[0] ?? dialog
    firstFocusable?.focus()

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        onClose()
        return
      }

      if (event.key !== 'Tab') return

      const currentFocusable = getFocusableElements(dialogRef.current)
      if (currentFocusable.length === 0) {
        event.preventDefault()
        dialogRef.current?.focus()
        return
      }

      const first = currentFocusable[0]
      const last = currentFocusable[currentFocusable.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      previousFocus?.focus()
    }
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        className="w-full max-w-sm rounded-lg border border-slate-800 bg-[#10161d] p-5 shadow-2xl outline-none"
      >
        <div className="mb-5 flex items-center justify-between gap-3">
          <h2 id={titleId} className="text-lg font-bold text-white">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-900 hover:text-white focus:outline-none focus:ring-2 focus:ring-red-500"
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

function getFocusableElements(root: HTMLElement | null) {
  if (!root) return []
  return Array.from(
    root.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((element) => !element.hasAttribute('aria-hidden'))
}
