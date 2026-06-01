import {
  Activity,
  BarChart3,
  Bell,
  Briefcase,
  Database,
  Home,
  LineChart,
  MessageSquare,
  PenLine,
  Settings,
  ShieldCheck,
  Wrench,
} from 'lucide-react'

export const primaryNavItems = [
  { href: '/', label: '工作台', icon: Home },
  { href: '/products', label: '行情', icon: LineChart },
  { href: '/workspace', label: '我的', icon: Briefcase },
  { href: '/my-comments', label: '评论', icon: MessageSquare },
  { href: '/metrics', label: '指标', icon: BarChart3 },
]

export interface SecondaryNavItem {
  label: string
  icon: React.ElementType
  href?: string
}

export interface NavGroup {
  title: string
  items: SecondaryNavItem[]
}

export const secondaryNavGroups: NavGroup[] = [
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
      { label: '新闻资讯', icon: Database, href: '/news' },
      { label: '交易观点', icon: PenLine, href: '/opinions' },
      { label: '提醒事件', icon: Bell },
    ],
  },
  {
    title: 'SYSTEM',
    items: [
      { label: '工具', icon: Wrench },
      { label: '设置', icon: Settings, href: '/settings' },
    ],
  },
]

export function isActivePath(pathname: string, href: string) {
  if (href === '/') return pathname === '/'
  return pathname === href || pathname.startsWith(`${href}/`)
}
