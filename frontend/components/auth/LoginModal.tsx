'use client'

import { useForm } from 'react-hook-form'
import { useAuth } from '@/components/auth/AuthProvider'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import ModalShell from './ModalShell'
import { User } from '@/lib/api'
import { captureMessage } from '@/lib/sentry-lite'

interface LoginForm {
  username: string
  password: string
}

interface LoginModalProps {
  onClose: () => void
  onSuccess: (user: User) => void
  onSwitchToRegister: () => void
}

export default function LoginModal({ onClose, onSuccess, onSwitchToRegister }: LoginModalProps) {
  const { login } = useAuth()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginForm>()

  const onSubmit = handleSubmit(async (data) => {
    try {
      const user = await login(data.username, data.password)
      captureMessage(`用户登录成功: ${user.username}`, 'info')
      onSuccess(user)
    } catch (err) {
      captureMessage(`用户登录失败: ${data.username}`, 'error')
      setError('root', {
        message: err instanceof Error ? err.message : '登录失败',
      })
    }
  })

  return (
    <ModalShell title="登录" onClose={onClose}>
      <form onSubmit={onSubmit} className="space-y-4">
        {errors.root && (
          <div className="rounded-lg bg-red-500/10 p-2 text-sm text-red-300">{errors.root.message}</div>
        )}
        <div>
          <label htmlFor="login-username" className="mb-1 block text-sm text-slate-400">用户名</label>
          <Input
            id="login-username"
            type="text"
            autoFocus
            {...register('username', { required: '请输入用户名' })}
          />
          {errors.username && <p className="mt-1 text-xs text-red-400">{errors.username.message}</p>}
        </div>
        <div>
          <label htmlFor="login-password" className="mb-1 block text-sm text-slate-400">密码</label>
          <Input
            id="login-password"
            type="password"
            {...register('password', { required: '请输入密码' })}
          />
          {errors.password && <p className="mt-1 text-xs text-red-400">{errors.password.message}</p>}
        </div>
        <Button type="submit" isLoading={isSubmitting} className="w-full">
          登录
        </Button>
      </form>
      <div className="mt-4 text-center text-sm text-slate-400">
        还没有账号？{' '}
        <button type="button" onClick={onSwitchToRegister} className="text-red-400 hover:underline">
          注册
        </button>
      </div>
    </ModalShell>
  )
}
