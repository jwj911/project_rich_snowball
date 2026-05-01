import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: '期货交流社区',
  description: '期货品种数据展示与评论社区',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  )
}
