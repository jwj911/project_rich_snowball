'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { FormEvent, ReactNode, useEffect, useState } from 'react'
import { User } from '@/lib/api'
import { useAuth } from '@/components/auth/AuthProvider'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import {
  Activity,
  Bell,
  Bot,
  Briefcase,
  Database,
  Home,
  LineChart,
  LogIn,
  LogOut,
  MessageSquare,
  Settings,
  ShieldCheck,
  Wrench,
  X,
} from 'lucide-react'

const primaryItems = [
  { href: '/', label: '工作台', icon: Home },
  { href: '/products', label: '行情', icon: LineChart },
  { href: '/workspace', label: '我的', icon: Briefcase },
  { href: '/my-comments', label: '评论', icon: MessageSquare },
]

const secondaryGroups = [
  {
    title: 'AGENT',
    items: [
      { label: 'Agent 状态', icon: Activity },
      { label: '权限心跳', icon: ShieldCheck },
    ],
  },
  {
    title: 'DATA',
    items: [
      { label: '市场数据', icon: Database },
      { label: '提醒事件', icon: Bell },
    ],
  },
  {
    title: 'SYSTEM',
    items: [
      { label: '工具', icon: Wrench },
      { label: '设置', icon: Settings },
    ],
  },
]

export default function Navbar() {
  const pathname = usePathname()
  const { user, logout } = useAuth()
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [showRegisterModal, setShowRegisterModal] = useState(false)

  useEffect(() => {
    const handleOpenLogin = () => setShowLoginModal(true)
    window.addEventListener('open-login-modal', handleOpenLogin)
    return () => window.removeEventListener('open-login-modal', handleOpenLogin)
  }, [])

  const openRegister = () => {
    setShowLoginModal(false)
    setShowRegisterModal(true)
  }

  return (
    <>
      <nav className="fixed inset-y-0 left-0 z-40 hidden w-48 border-r border-slate-800 bg-[#10161d] text-slate-300 md:flex md:flex-col">
        <div className="flex h-20 items-center gap-2.5 border-b border-slate-800 px-4">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-red-900/60 bg-red-950/40 text-red-300">
            <Bot size={20} />
          </div>
          <Link href="/" className="text-base font-semibold text-white">
            倍增计划
          </Link>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-5">
          <div className="space-y-1">
            {primaryItems.map((item) => (
              <NavLink key={item.href} item={item} isActive={isActivePath(pathname, item.href)} />
            ))}
          </div>

          <div className="mt-8 space-y-7">
            {secondaryGroups.map((group) => (
              <div key={group.title}>
                <div className="mb-2 px-2.5 text-xs font-semibold uppercase tracking-wider text-slate-600">
                  {group.title}
                </div>
                <div className="space-y-1">
                  {group.items.map((item) => (
                    <div
                      key={item.label}
                      className="flex items-center gap-2.5 rounded-lg px-2.5 py-2.5 text-sm text-slate-500"
                    >
                      <item.icon size={17} />
                      {item.label}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-3 border-t border-slate-800 p-4">
          {user ? (
            <>
              <div className="rounded-lg border border-slate-800 bg-black/40 px-3 py-2">
                <div className="text-xs text-slate-500">当前用户</div>
                <div className="mt-1 truncate text-sm font-medium text-white">{user.username}</div>
              </div>
              <button
                type="button"
                onClick={logout}
                className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-slate-900 hover:text-white"
              >
                <LogOut size={16} />
                退出
              </button>
            </>
          ) : (
            <div className="grid gap-2">
              <Button type="button" onClick={() => setShowLoginModal(true)} className="w-full">
                <LogIn size={16} />
                登录
              </Button>
              <Button type="button" variant="ghost" onClick={openRegister} className="w-full">
                注册
              </Button>
            </div>
          )}
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            私密工作台
          </div>
        </div>
      </nav>

      <nav className="sticky top-0 z-40 border-b border-slate-800 bg-[#10161d] md:hidden">
        <div className="flex h-14 min-w-0 items-center justify-between gap-3 px-4">
          <Link href="/" className="font-semibold text-white">
            倍增计划
          </Link>
          {user ? (
            <button
              type="button"
              onClick={logout}
              className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm text-slate-400 transition hover:bg-slate-900 hover:text-white"
            >
              <LogOut size={14} />
              退出
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setShowLoginModal(true)}
              className="inline-flex items-center gap-1 rounded-lg bg-red-600 px-3 py-1.5 text-sm text-white transition-colors hover:bg-red-700"
            >
              <LogIn size={14} />
              登录
            </button>
          )}
        </div>
        <div className="grid grid-cols-4 border-t border-slate-800">
          {primaryItems.map((item) => {
            const isActive = isActivePath(pathname, item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center justify-center gap-1.5 px-2 py-2 text-xs transition-colors ${
                  isActive ? 'text-red-300' : 'text-slate-500 hover:text-slate-200'
                }`}
              >
                <item.icon size={15} />
                {item.label}
              </Link>
            )
          })}
        </div>
      </nav>

      {showLoginModal && (
        <LoginModal
          onClose={() => setShowLoginModal(false)}
          onSuccess={() => setShowLoginModal(false)}
          onSwitchToRegister={openRegister}
        />
      )}

      {showRegisterModal && (
        <RegisterModal
          onClose={() => setShowRegisterModal(false)}
          onSuccess={() => {
            setShowRegisterModal(false)
            setShowLoginModal(true)
          }}
        />
      )}
    </>
  )
}

function isActivePath(pathname: string, href: string) {
  if (href === '/') return pathname === '/'
  return pathname === href || pathname.startsWith(`${href}/`)
}

function NavLink({
  item,
  isActive,
}: {
  item: typeof primaryItems[number]
  isActive: boolean
}) {
  return (
    <Link
      href={item.href}
      className={`relative flex items-center gap-2.5 rounded-lg px-2.5 py-3 text-sm font-medium transition-colors ${
        isActive ? 'bg-slate-800 text-white' : 'text-slate-400 hover:bg-slate-900 hover:text-white'
      }`}
    >
      {isActive && <span className="absolute left-0 h-7 w-1 rounded-r bg-red-500" />}
      <item.icon size={18} />
      {item.label}
    </Link>
  )
}

function ModalShell({
  title,
  children,
  onClose,
}: {
  title: string
  children: ReactNode
  onClose: () => void
}) {
  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="w-full max-w-sm rounded-lg border border-slate-800 bg-[#10161d] p-5 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-5 flex items-center justify-between gap-3">
          <h2 className="text-lg font-bold text-white">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-900 hover:text-white"
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

function LoginModal({
  onClose,
  onSuccess,
  onSwitchToRegister,
}: {
  onClose: () => void
  onSuccess: (user: User) => void
  onSwitchToRegister: () => void
}) {
  const { login } = useAuth()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setLoading(true)

    try {
      const currentUser = await login(username, password)
      onSuccess(currentUser)
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ModalShell title="登录" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <div className="rounded-lg bg-red-500/10 p-2 text-sm text-red-300">{error}</div>}
        <div>
          <label className="mb-1 block text-sm text-slate-400">用户名</label>
          <Input type="text" value={username} onChange={(event) => setUsername(event.target.value)} required />
        </div>
        <div>
          <label className="mb-1 block text-sm text-slate-400">密码</label>
          <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </div>
        <Button type="submit" isLoading={loading} className="w-full">
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

function RegisterModal({ onClose, onSuccess }: { onClose: () => void; onSuccess: () => void }) {
  const { register } = useAuth()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    setError('')
    setLoading(true)

    try {
      await register(username, email, password)
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <ModalShell title="注册" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && <div className="rounded-lg bg-red-500/10 p-2 text-sm text-red-300">{error}</div>}
        <div>
          <label className="mb-1 block text-sm text-slate-400">用户名</label>
          <Input type="text" value={username} onChange={(event) => setUsername(event.target.value)} required />
        </div>
        <div>
          <label className="mb-1 block text-sm text-slate-400">邮箱</label>
          <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
        </div>
        <div>
          <label className="mb-1 block text-sm text-slate-400">密码</label>
          <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        </div>
        <Button type="submit" isLoading={loading} className="w-full">
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
