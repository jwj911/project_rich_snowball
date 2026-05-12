import { ButtonHTMLAttributes } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  isLoading?: boolean
}

const variants = {
  primary: 'bg-red-600 text-white hover:bg-red-700 disabled:hover:bg-red-600',
  secondary: 'bg-slate-700 text-slate-100 hover:bg-slate-600 disabled:hover:bg-slate-700',
  ghost: 'text-slate-400 hover:text-white hover:bg-slate-700/60 disabled:hover:bg-transparent',
  danger: 'bg-red-600 text-white hover:bg-red-700 disabled:hover:bg-red-600',
}

export default function Button({
  variant = 'primary',
  isLoading = false,
  disabled,
  className = '',
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${variants[variant]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? '处理中...' : children}
    </button>
  )
}
