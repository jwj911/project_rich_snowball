import Link from 'next/link'
import { LogIn, LogOut } from 'lucide-react'
import { User } from '@/lib/api'
import { isActivePath, primaryNavItems } from '@/components/layout/navigation'

interface MobileNavProps {
  pathname: string
  user: User | null
  onLogin: () => void
  onLogout: () => void
}

export default function MobileNav({
  pathname,
  user,
  onLogin,
  onLogout,
}: MobileNavProps) {
  return (
    <nav className="sticky top-0 z-40 border-b border-slate-800 bg-surface md:hidden">
      <div className="flex h-14 min-w-0 items-center justify-between gap-3 px-4">
        <Link href="/" className="min-w-0">
          <span className="block text-sm font-semibold leading-tight text-white">倍增计划</span>
          <span className="block text-[11px] font-medium leading-tight text-slate-500">BullZone</span>
        </Link>
        {user ? (
          <button
            type="button"
            onClick={onLogout}
            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-sm text-slate-400 transition hover:bg-slate-900 hover:text-white"
          >
            <LogOut size={14} />
            退出
          </button>
        ) : (
          <button
            type="button"
            onClick={onLogin}
            className="inline-flex items-center gap-1 rounded-lg bg-red-600 px-3 py-1.5 text-sm text-white transition-colors hover:bg-red-700"
          >
            <LogIn size={14} />
            登录
          </button>
        )}
      </div>
      <div className="grid grid-cols-4 border-t border-slate-800">
        {primaryNavItems.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`flex items-center justify-center gap-1.5 px-2 py-2 text-xs transition-colors ${
              isActivePath(pathname, item.href) ? 'text-red-300' : 'text-slate-500 hover:text-slate-200'
            }`}
          >
            <item.icon size={15} />
            {item.label}
          </Link>
        ))}
      </div>
    </nav>
  )
}
