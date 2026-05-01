'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import { api, Comment, User } from '@/lib/api'
import { MessageSquare } from 'lucide-react'

export default function MyCommentsPage() {
  const [comments, setComments] = useState<Comment[]>([])
  const [loading, setLoading] = useState(true)
  const [user, setUser] = useState<User | null>(null)

  useEffect(() => {
    const token = api.getToken()
    if (token) {
      api.getMe().then(u => {
        setUser(u)
        return api.getUserComments(u.username)
      }).then(setComments).catch(() => {
        api.logout()
      }).finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [])

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  if (!api.getToken()) {
    return (
      <div className="min-h-screen bg-slate-900">
        <Navbar />
        <main className="max-w-4xl mx-auto px-4 py-8">
          <div className="bg-slate-800 rounded-xl p-8 border border-slate-700 text-center">
            <MessageSquare size={48} className="mx-auto text-slate-600 mb-4" />
            <h2 className="text-xl font-bold text-white mb-2">请先登录</h2>
            <p className="text-slate-400">登录后即可查看您的评论记录</p>
          </div>
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-900">
      <Navbar />
      <main className="max-w-4xl mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white mb-2">我的评论</h1>
          <p className="text-slate-400">
            {user ? `欢迎，${user.username}` : '加载中...'}
          </p>
        </div>

        {loading ? (
          <div className="space-y-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="bg-slate-800 rounded-xl p-4 animate-pulse">
                <div className="h-4 bg-slate-700 rounded w-1/4 mb-2"></div>
                <div className="h-3 bg-slate-700 rounded w-3/4"></div>
              </div>
            ))}
          </div>
        ) : comments.length === 0 ? (
          <div className="bg-slate-800 rounded-xl p-8 border border-slate-700 text-center">
            <MessageSquare size={48} className="mx-auto text-slate-600 mb-4" />
            <h2 className="text-xl font-bold text-white mb-2">暂无评论</h2>
            <p className="text-slate-400">快去品种详情页发表你的看法吧！</p>
            <Link
              href="/products"
              className="inline-block mt-4 px-4 py-2 bg-cyan-600 text-white rounded-lg hover:bg-cyan-700 transition-colors"
            >
              浏览品种
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            {comments.map(comment => (
              <Link key={comment.id} href={`/products/${comment.product_id}`}>
                <div className="bg-slate-800 rounded-xl p-4 border border-slate-700 hover:border-slate-600 transition-colors">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-cyan-400 text-sm">品种 #{comment.product_id}</span>
                    <span className="text-slate-500 text-xs">{formatDate(comment.created_at)}</span>
                  </div>
                  <p className="text-slate-300 text-sm leading-relaxed">{comment.content}</p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
