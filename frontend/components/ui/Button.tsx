import { ButtonHTMLAttributes, ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'tertiary' | 'danger' | 'ghost'
export type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  isLoading?: boolean
  leftIcon?: ReactNode
  rightIcon?: ReactNode
}

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    'bg-gray-1000 text-background hover:bg-gray-900 active:bg-gray-800 disabled:hover:bg-gray-1000',
  secondary:
    'border border-gray-alpha-400 bg-background text-foreground hover:border-gray-alpha-500 hover:bg-gray-alpha-100 active:bg-gray-alpha-200 disabled:hover:bg-background',
  tertiary:
    'bg-transparent text-foreground hover:bg-gray-alpha-200 active:bg-gray-alpha-300 disabled:hover:bg-transparent',
  danger:
    'bg-red-800 text-white hover:bg-red-700 active:bg-red-600 disabled:hover:bg-red-800',
  ghost:
    'bg-transparent text-gray-900 hover:text-foreground hover:bg-gray-alpha-200 active:bg-gray-alpha-300 disabled:hover:bg-transparent',
}

const sizeClasses: Record<ButtonSize, string> = {
  sm: 'h-8 px-2 text-sm',
  md: 'h-10 px-2.5 text-sm',
  lg: 'h-12 px-3.5 text-base',
}

export default function Button({
  variant = 'primary',
  size = 'md',
  isLoading = false,
  disabled,
  className = '',
  children,
  leftIcon,
  rightIcon,
  ...props
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-ring ${variantClasses[variant]} ${sizeClasses[size]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <>
          <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" />
          处理中…
        </>
      ) : (
        <>
          {leftIcon}
          {children}
          {rightIcon}
        </>
      )}
    </button>
  )
}
