import Link from 'next/link'
import { Bot, LogIn, LogOut } from 'lucide-react'
import { User } from '@/lib/api'
import Button from '@/components/ui/Button'
import { isActivePath, primaryNavItems, secondaryNavGroups } from '@/components/layout/navigation'

interface SideNavProps {
  pathname: string
  user: User | null
  onLogin: () => void
  onRegister: () => void
  onLogout: () => void
}

export default function SideNav({
  pathname,
  user,
  onLogin,
  onRegister,
  onLogout,
}: SideNavProps) {
  return (
    <nav className="fixed inset-y-0 left-0 z-40 hidden w-48 border-r border-slate-800 bg-[#10161d] text-slate-300 md:flex md:flex-col">
      <div className="flex h-20 items-center gap-2.5 border-b border-slate-800 px-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-red-900/60 bg-red-950/40 text-red-300">
          <Bot size={20} />
        </div>
        <Link href="/" className="min-w-0">
          <span className="block text-base font-semibold leading-tight text-white">倍增计划</span>
          <span className="block text-xs font-medium leading-tight text-slate-500">BullZone</span>
        </Link>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-5">
        <div className="space-y-1">
          {primaryNavItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`relative flex items-center gap-2.5 rounded-lg px-2.5 py-3 text-sm font-medium transition-colors ${
                isActivePath(pathname, item.href)
                  ? 'bg-slate-800 text-white'
                  : 'text-slate-400 hover:bg-slate-900 hover:text-white'
              }`}
            >
              {isActivePath(pathname, item.href) && <span className="absolute left-0 h-7 w-1 rounded-r bg-red-500" />}
              <item.icon size={18} />
              {item.label}
            </Link>
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
              onClick={onLogout}
              className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm text-slate-400 transition-colors hover:bg-slate-900 hover:text-white"
            >
              <LogOut size={16} />
              退出
            </button>
          </>
        ) : (
          <div className="grid gap-2">
            <Button type="button" onClick={onLogin} className="w-full">
              <LogIn size={16} />
              登录
            </Button>
            <Button type="button" variant="ghost" onClick={onRegister} className="w-full">
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
  )
}
