'use client'

import { useForm } from 'react-hook-form'
import { useAuth } from '@/components/auth/AuthProvider'
import { captureMessage } from '@/lib/sentry-lite'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import ModalShell from './ModalShell'

interface RegisterForm {
  username: string
  email: string
  password: string
}

interface RegisterModalProps {
  onClose: () => void
  onSuccess: () => void
}

export default function RegisterModal({ onClose, onSuccess }: RegisterModalProps) {
  const { register: registerUser } = useAuth()
  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterForm>()

  const onSubmit = handleSubmit(async (data) => {
    try {
      await registerUser(data.username, data.email, data.password)
      captureMessage(`用户注册成功: ${data.username}`, 'info')
      onSuccess()
    } catch (err) {
      captureMessage(`用户注册失败: ${data.username}`, 'error')
      setError('root', {
        message: err instanceof Error ? err.message : '注册失败',
      })
    }
  })

  return (
    <ModalShell title="注册" onClose={onClose}>
      <form onSubmit={onSubmit} className="space-y-4">
        {errors.root && (
          <div className="rounded-lg bg-red-500/10 p-2 text-sm text-red-300">{errors.root.message}</div>
        )}
        <div>
          <label htmlFor="register-username" className="mb-1 block text-sm text-slate-400">用户名</label>
          <Input
            id="register-username"
            type="text"
            {...register('username', { required: '请输入用户名' })}
          />
          {errors.username && <p className="mt-1 text-xs text-red-400">{errors.username.message}</p>}
        </div>
        <div>
          <label htmlFor="register-email" className="mb-1 block text-sm text-slate-400">邮箱</label>
          <Input
            id="register-email"
            type="email"
            {...register('email', {
              required: '请输入邮箱',
              pattern: { value: /\S+@\S+\.\S+/, message: '邮箱格式不正确' },
            })}
          />
          {errors.email && <p className="mt-1 text-xs text-red-400">{errors.email.message}</p>}
        </div>
        <div>
          <label htmlFor="register-password" className="mb-1 block text-sm text-slate-400">密码</label>
          <Input
            id="register-password"
            type="password"
            {...register('password', {
              required: '请输入密码',
              minLength: { value: 6, message: '密码至少 6 位' },
            })}
          />
          {errors.password && <p className="mt-1 text-xs text-red-400">{errors.password.message}</p>}
        </div>
        <Button type="submit" isLoading={isSubmitting} className="w-full">
          注册
        </Button>
      </form>
      <div className="mt-4 text-center text-sm text-slate-400">
        已有账号？{' '}
        <button
          type="button"
          onClick={() => {
            onClose()
            window.dispatchEvent(new Event('open-login-modal'))
          }}
          className="text-red-400 hover:underline"
        >
          去登录
        </button>
      </div>
    </ModalShell>
  )
}
