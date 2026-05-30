'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '@/components/auth/AuthProvider'
import LoginModal from '@/components/auth/LoginModal'
import RegisterModal from '@/components/auth/RegisterModal'
import Button from '@/components/ui/Button'
import { Bot, LogIn, LogOut } from 'lucide-react'
import { primaryNavItems, secondaryNavGroups } from '@/components/layout/navigation'

export default function Navbar() {
  const pathname = usePathname()
  const { user, logout } = useAuth()
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [showRegisterModal, setShowRegisterModal] = useState(false)
  const triggerRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    const handleOpenLogin = () => {
      triggerRef.current = document.activeElement as HTMLElement
      setShowLoginModal(true)
    }
    window.addEventListener('open-login-modal', handleOpenLogin)
    return () => window.removeEventListener('open-login-modal', handleOpenLogin)
  }, [])

  const openLogin = () => {
    triggerRef.current = document.activeElement as HTMLElement
    setShowLoginModal(true)
  }

  const closeLogin = () => {
    setShowLoginModal(false)
    // 恢复焦点到触发按钮
    setTimeout(() => triggerRef.current?.focus(), 0)
  }

  const openRegister = () => {
    setShowLoginModal(false)
    setShowRegisterModal(true)
  }

  return (
    <>
      <nav className="fixed inset-y-0 left-0 z-40 hidden w-48 border-r border-slate-800 bg-surface text-slate-300 md:flex md:flex-col">
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
            {primaryNavItems.map((item) => (
              <NavLink key={item.href} item={item} isActive={isActivePath(pathname, item.href)} />
            ))}
          </div>

          <div className="mt-8 space-y-7">
            {secondaryNavGroups.map((group) => (
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
              <Button type="button" onClick={openLogin} className="w-full">
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

      <nav className="sticky top-0 z-40 border-b border-slate-800 bg-surface md:hidden">
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
              onClick={openLogin}
              className="inline-flex items-center gap-1 rounded-lg bg-red-600 px-3 py-1.5 text-sm text-white transition-colors hover:bg-red-700"
            >
              <LogIn size={14} />
              登录
            </button>
          )}
        </div>
        <div className="grid grid-cols-5 border-t border-slate-800">
          {primaryNavItems.map((item) => {
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
          onClose={closeLogin}
          onSuccess={closeLogin}
          onSwitchToRegister={openRegister}
        />
      )}

      {showRegisterModal && (
        <RegisterModal
          onClose={() => setShowRegisterModal(false)}
          onSuccess={() => {
            setShowRegisterModal(false)
            openLogin()
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
  item: typeof primaryNavItems[number]
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
