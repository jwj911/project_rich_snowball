import { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  shadow?: 'none' | 'raised'
  padding?: 'none' | 'sm' | 'md' | 'lg'
}

const paddingClasses = {
  none: '',
  sm: 'p-4',
  md: 'p-5',
  lg: 'p-6',
}

export default function Card({
  children,
  className = '',
  shadow = 'none',
  padding = 'md',
}: CardProps) {
  return (
    <div
      className={`rounded border border-gray-alpha-400 bg-background ${paddingClasses[padding]} ${shadow === 'raised' ? 'shadow-raised' : ''} ${className}`}
    >
      {children}
    </div>
  )
}
