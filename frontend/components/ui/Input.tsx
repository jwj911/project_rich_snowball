import { forwardRef, InputHTMLAttributes } from 'react'

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  inputSize?: 'sm' | 'md' | 'lg'
}

const sizeClasses = {
  sm: 'h-8 px-3 text-sm',
  md: 'h-10 px-3 text-sm',
  lg: 'h-12 px-3 text-base',
}

const Input = forwardRef<HTMLInputElement, InputProps>(
  function Input({ className = '', inputSize = 'md', ...props }, ref) {
    return (
      <input
        ref={ref}
        className={`w-full rounded border border-gray-alpha-400 bg-background text-foreground outline-none transition-colors placeholder:text-gray-900 hover:border-gray-alpha-500 focus:border-gray-alpha-500 focus:shadow-[0_0_0_2px_#000000,0_0_0_4px_#47a8ff] disabled:cursor-not-allowed disabled:opacity-50 ${sizeClasses[inputSize]} ${className}`}
        {...props}
      />
    )
  }
)

export default Input
