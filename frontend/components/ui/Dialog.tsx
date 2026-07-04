import { ReactNode, useEffect, useRef } from 'react'

interface DialogProps {
  open: boolean
  onClose: () => void
  children: ReactNode
  className?: string
  title?: ReactNode
}

export default function Dialog({ open, onClose, children, className = '', title }: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [open, onClose])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose()
      }}
    >
      <div className="absolute inset-0 bg-black/60" />
      <div
        ref={panelRef}
        className={`relative w-full max-w-lg rounded-md border border-gray-alpha-400 bg-background p-5 shadow-modal ${className}`}
      >
        {title && <div className="mb-4 text-heading-16 text-foreground">{title}</div>}
        {children}
      </div>
    </div>
  )
}
