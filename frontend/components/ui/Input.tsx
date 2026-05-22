import { forwardRef, InputHTMLAttributes } from 'react'

const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className = '', ...props }, ref) {
    return (
      <input
        ref={ref}
        className={`w-full rounded-lg border border-slate-600 bg-slate-900 px-3 py-2 text-sm text-white outline-none transition-colors placeholder:text-slate-500 focus:border-red-500 ${className}`}
        {...props}
      />
    )
  }
)

export default Input
