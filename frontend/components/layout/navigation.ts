import {
  Activity,
  Bell,
  Briefcase,
  Database,
  Home,
  LineChart,
  MessageSquare,
  Settings,
  ShieldCheck,
  Wrench,
} from 'lucide-react'

export const primaryNavItems = [
  { href: '/', label: '工作台', icon: Home },
  { href: '/products', label: '行情', icon: LineChart },
  { href: '/workspace', label: '我的', icon: Briefcase },
  { href: '/my-comments', label: '评论', icon: MessageSquare },
]

export const secondaryNavGroups = [
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

export function isActivePath(pathname: string, href: string) {
  if (href === '/') return pathname === '/'
  return pathname === href || pathname.startsWith(`${href}/`)
}
