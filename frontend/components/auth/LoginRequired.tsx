'use client'

import { LogIn, LockKeyhole } from 'lucide-react'
import Button from '@/components/ui/Button'

interface LoginRequiredProps {
  title?: string
  description?: string
}

export default function LoginRequired({
  title = '倍增计划是私密交流社区',
  description = '登录并确认权限后，可以查看行情、评论及相关策略。',
}: LoginRequiredProps) {
  const openLogin = () => {
    window.dispatchEvent(new Event('open-login-modal'))
  }

  return (
    <div className="flex min-h-[calc(100vh-8rem)] w-full flex-col items-center justify-center rounded-lg border border-red-950/70 bg-black p-8 text-center">
      <LockKeyhole size={42} className="mx-auto mb-4 text-red-500" />
      <h1 className="mb-2 text-xl font-semibold text-white">{title}</h1>
      <p className="mx-auto max-w-md text-sm leading-6 text-slate-400">{description}</p>
      <Button type="button" onClick={openLogin} className="mt-6 min-w-40">
        <LogIn size={16} />
        登录
      </Button>
    </div>
  )
}
