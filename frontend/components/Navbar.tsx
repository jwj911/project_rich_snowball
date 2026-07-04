'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { useAuth } from '@/components/auth/AuthProvider'
import LoginModal from '@/components/auth/LoginModal'
import RegisterModal from '@/components/auth/RegisterModal'
import Button from '@/components/ui/Button'
import { Bot, LogIn, LogOut } from 'lucide-react'
import { isActivePath, primaryNavItems, secondaryNavGroups } from '@/components/layout/navigation'

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
    setTimeout(() => triggerRef.current?.focus(), 0)
  }

  const openRegister = () => {
    setShowLoginModal(false)
    setShowRegisterModal(true)
  }

  return (
    <>
      <nav className="fixed inset-y-0 left-0 z-40 hidden w-44 flex-col border-r border-gray-alpha-400 bg-background md:flex">
        <div className="flex h-16 items-center gap-2.5 border-b border-gray-alpha-400 px-3">
          <div className="flex h-8 w-8 items-center justify-center rounded border border-gray-alpha-400 bg-gray-100 text-foreground">
            <Bot size={18} />
          </div>
          <Link href="/" className="text-heading-14 text-foreground">
            倍增计划
          </Link>
        </div>

        <div className="flex-1 overflow-y-auto px-2 py-4">
          <div className="space-y-0.5">
            {primaryNavItems.map((item) => (
              <NavLink key={item.href} item={item} isActive={isActivePath(pathname, item.href)} />
            ))}
          </div>

          <div className="mt-6 space-y-5">
            {secondaryNavGroups.map((group) => (
              <div key={group.title}>
                <div className="mb-1.5 px-2.5 text-label-12 uppercase tracking-wider text-gray-800">
                  {group.title}
                </div>
                <div className="space-y-0.5">
                  {group.items.map((item) =>
                    item.href ? (
                      <Link
                        key={item.label}
                        href={item.href}
                        className={`flex items-center gap-2.5 rounded px-2.5 py-2 text-label-14 transition-colors ${
                          isActivePath(pathname, item.href)
                            ? 'bg-gray-300 text-foreground'
                            : 'text-gray-800 hover:bg-gray-alpha-200 hover:text-foreground'
                        }`}
                      >
                        <item.icon size={16} />
                        {item.label}
                      </Link>
                    ) : (
                      <div
                        key={item.label}
                        className="flex items-center gap-2.5 rounded px-2.5 py-2 text-label-14 text-gray-600"
                      >
                        <item.icon size={16} />
                        {item.label}
                      </div>
                    ),
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-3 border-t border-gray-alpha-400 p-3">
          {user ? (
            <>
              <div className="rounded border border-gray-alpha-400 bg-gray-100 px-3 py-2">
                <div className="text-label-12 text-gray-800">当前用户</div>
                <div className="mt-1 truncate text-label-14 text-foreground">{user.username}</div>
              </div>
              <button
                type="button"
                onClick={logout}
                className="flex w-full items-center gap-2 rounded px-3 py-2 text-label-14 text-gray-800 transition-colors hover:bg-gray-alpha-200 hover:text-foreground"
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
              <Button type="button" variant="secondary" onClick={openRegister} className="w-full">
                注册
              </Button>
            </div>
          )}
          <div className="flex items-center gap-2 text-label-12 text-gray-800">
            <span className="h-2 w-2 rounded-full bg-green-700" />
            私密工作台
          </div>
        </div>
      </nav>

      <nav className="sticky top-0 z-40 border-b border-gray-alpha-400 bg-background md:hidden">
        <div className="flex h-14 min-w-0 items-center justify-between gap-3 px-4">
          <Link href="/" className="text-heading-14 text-foreground">
            倍增计划
          </Link>
          {user ? (
            <button
              type="button"
              onClick={logout}
              className="inline-flex items-center gap-1 rounded px-2.5 py-1.5 text-label-14 text-gray-800 transition hover:bg-gray-alpha-200 hover:text-foreground"
            >
              <LogOut size={14} />
              退出
            </button>
          ) : (
            <Button type="button" size="sm" onClick={openLogin}>
              <LogIn size={14} />
              登录
            </Button>
          )}
        </div>
        <div className="grid grid-cols-5 border-t border-gray-alpha-400">
          {primaryNavItems.map((item) => {
            const isActive = isActivePath(pathname, item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center justify-center gap-1 px-2 py-2 text-label-12 transition-colors ${
                  isActive ? 'text-foreground' : 'text-gray-800 hover:text-gray-900'
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
      className={`relative flex items-center gap-2.5 rounded px-2.5 py-2.5 text-label-14 transition-colors ${
        isActive ? 'bg-gray-300 text-foreground' : 'text-gray-800 hover:bg-gray-alpha-200 hover:text-foreground'
      }`}
    >
      <item.icon size={18} />
      {item.label}
    </Link>
  )
}
