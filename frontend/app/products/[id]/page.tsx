'use client'

import { useEffect, useState, useRef } from 'react'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import KlineChart from '@/components/KlineChart'
import { api, Product, Comment } from '@/lib/api'
import { ArrowLeft, Send, TrendingUp, TrendingDown, DollarSign, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react'

export default function ProductDetailPage({ params }: { params: { id: string } }) {
  const { id } = params
  const [product, setProduct] = useState<Product | null>(null)
  const [comments, setComments] = useState<Comment[]>([])
  const [newComment, setNewComment] = useState('')
  const [user, setUser] = useState<any>(null)
  const [isLoading, setIsLoading] = useState(true)

  const [supportLevels, setSupportLevels] = useState<number[]>([])
  const [resistanceLevels, setResistanceLevels] = useState<number[]>([])
  const [newSupport, setNewSupport] = useState('')
  const [newResistance, setNewResistance] = useState('')

  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const loadData = async () => {
      try {
        const data = await api.getProduct(parseInt(id))
        setProduct(data.product)
        setComments(data.comments)
      } catch (error) {
        console.error('Failed to load product:', error)
      } finally {
        setIsLoading(false)
      }
    }

    const checkAuth = async () => {
      if (api.getToken()) {
        try {
          const userData = await api.getMe()
          setUser(userData)
        } catch (e) {
          console.error('Auth check failed')
        }
      }
    }

    loadData()
    checkAuth()
  }, [id])

  const handleSubmitComment = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newComment.trim() || !user) return

    try {
      const comment = await api.createComment(parseInt(id), newComment)
      setComments(prev => [comment, ...prev])
      setNewComment('')
    } catch (error) {
      console.error('Failed to post comment:', error)
    }
  }

  const handleAddSupport = (price: number) => {
    if (!supportLevels.includes(price)) {
      setSupportLevels([...supportLevels, price].sort((a, b) => a - b))
    }
  }

  const handleAddResistance = (price: number) => {
    if (!resistanceLevels.includes(price)) {
      setResistanceLevels([...resistanceLevels, price].sort((a, b) => b - a))
    }
  }

  const handleRemoveSupport = (price: number) => {
    setSupportLevels(supportLevels.filter(p => p !== price))
  }

  const handleRemoveResistance = (price: number) => {
    setResistanceLevels(resistanceLevels.filter(p => p !== price))
  }

  const submitNewSupport = () => {
    const price = parseFloat(newSupport)
    if (!isNaN(price)) {
      handleAddSupport(price)
      setNewSupport('')
    }
  }

  const submitNewResistance = () => {
    const price = parseFloat(newResistance)
    if (!isNaN(price)) {
      handleAddResistance(price)
      setNewResistance('')
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#0f172a] text-white">
        <Navbar />
        <div className="container mx-auto p-4 text-center py-20">
          加载中...
        </div>
      </div>
    )
  }

  if (!product) {
    return (
      <div className="min-h-screen bg-[#0f172a] text-white">
        <Navbar />
        <div className="container mx-auto p-4 text-center py-20">
          品种不存在
        </div>
      </div>
    )
  }

  const isUp = (product.change_percent || 0) > 0
  const marginCost = product.margin ? (product.current_price || 0) * product.margin / 100 : 0

  return (
    <div className="min-h-screen bg-[#0f172a] text-white">
      <Navbar />
      <div className="flex h-[calc(100vh-60px)]">
        <div className="flex-1 flex flex-col p-4 gap-4 overflow-hidden">
          <div className="flex items-center justify-between mb-2">
            <Link href="/" className="flex items-center gap-2 text-gray-400 hover:text-white">
              <ArrowLeft size={16} />
              返回品种列表
            </Link>
            <div className="flex items-center gap-4">
              <span className="text-xl font-bold font-mono">{product.name} ({product.symbol})</span>
              <span className={`text-2xl font-bold font-mono ${isUp ? 'text-red-400' : 'text-green-400'}`}>
                {product.current_price?.toLocaleString() || '--'}
              </span>
              <span className={`text-lg font-mono ${isUp ? 'text-red-400' : 'text-green-400'}`}>
                {isUp ? '+' : ''}{product.change_percent?.toFixed(2)}%
              </span>
            </div>
          </div>

          <div className="flex-1 flex flex-col gap-4">
            <div className="flex-1">
              <KlineChart 
                data={[]}
                symbol={product.symbol}
                supportLevels={supportLevels}
                resistanceLevels={resistanceLevels}
                onAddSupport={handleAddSupport}
                onAddResistance={handleAddResistance}
                onRemoveSupport={handleRemoveSupport}
                onRemoveResistance={handleRemoveResistance}
              />
            </div>

            <div className="bg-[#131722] rounded-lg border border-[#2a2e39] p-3">
              <h3 className="text-sm font-semibold mb-2 flex items-center gap-2 text-gray-300">
                <Send size={16} /> 评论区
              </h3>
              
              {user ? (
                <form onSubmit={handleSubmitComment} className="flex gap-2 mb-3">
                  <input
                    type="text"
                    value={newComment}
                    onChange={(e) => setNewComment(e.target.value)}
                    placeholder="发表你的看法..."
                    className="flex-1 bg-[#1e222d] border border-[#2a2e39] rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-[#2962ff] placeholder-gray-500"
                  />
                  <button type="submit" className="bg-[#2962ff] hover:bg-[#1e4fd9] px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                    发送
                  </button>
                </form>
              ) : (
                <div className="text-sm text-gray-500 mb-3 flex items-center gap-2">
                  <AlertTriangle size={14} />
                  请先登录后评论
                </div>
              )}

              <div ref={scrollRef} className="space-y-2 max-h-40 overflow-y-auto pr-2">
                {comments.map((comment) => (
                  <div key={comment.id} className="bg-[#1e222d] rounded-lg px-3 py-2">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-xs font-semibold text-[#2962ff]">{comment.username}</span>
                      <span className="text-xs text-gray-500">{new Date(comment.created_at).toLocaleString()}</span>
                    </div>
                    <p className="text-sm text-gray-300">{comment.content}</p>
                  </div>
                ))}
                {comments.length === 0 && <p className="text-sm text-gray-500">暂无评论</p>}
              </div>
            </div>
          </div>
        </div>

        <div className="w-72 bg-[#131722] border-l border-[#2a2e39] flex flex-col overflow-hidden">
          <div className="p-4 border-b border-[#2a2e39]">
            <h3 className="font-semibold text-lg mb-3 flex items-center gap-2">
              <DollarSign size={18} /> 交易信息
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between text-gray-400">
                <span>保证金率</span>
                <span className="font-mono text-white">{product.margin}%</span>
              </div>
              <div className="flex justify-between text-gray-400">
                <span>预估保证金</span>
                <span className="font-mono text-green-400">{marginCost.toFixed(2)}</span>
              </div>
              <div className="flex justify-between text-gray-400">
                <span>手续费</span>
                <span className="font-mono text-white">{product.commission}元/手</span>
              </div>
              <div className="flex justify-between text-gray-400">
                <span>成交量</span>
                <span className="font-mono text-white">{product.volume?.toLocaleString() || '--'}</span>
              </div>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-6">
            <div>
              <h4 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
                <CheckCircle2 size={16} className="text-green-400" />
                支撑位
              </h4>
              <div className="space-y-2">
                <div className="flex gap-2">
                  <input
                    type="number"
                    placeholder="价格"
                    value={newSupport}
                    onChange={(e) => setNewSupport(e.target.value)}
                    className="w-full bg-[#1e222d] border border-[#2a2e39] rounded px-2 py-1 text-sm focus:border-[#22c55e] focus:outline-none"
                  />
                  <button
                    onClick={submitNewSupport}
                    className="bg-[#22c55e]/20 hover:bg-[#22c55e]/30 text-green-400 px-3 rounded text-sm font-medium transition"
                  >
                    添加
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {supportLevels.map((level, i) => (
                    <span
                      key={`s-${i}`}
                      onClick={() => handleRemoveSupport(level)}
                      className="flex items-center gap-1 bg-green-400/10 text-green-400 px-2 py-1 rounded text-xs cursor-pointer hover:bg-green-400/20 font-mono"
                    >
                      {level.toFixed(2)}
                      <XCircle size={12} />
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div>
              <h4 className="text-sm font-semibold text-gray-300 mb-3 flex items-center gap-2">
                <TrendingUp size={16} className="text-red-400" />
                阻力位
              </h4>
              <div className="space-y-2">
                <div className="flex gap-2">
                  <input
                    type="number"
                    placeholder="价格"
                    value={newResistance}
                    onChange={(e) => setNewResistance(e.target.value)}
                    className="w-full bg-[#1e222d] border border-[#2a2e39] rounded px-2 py-1 text-sm focus:border-[#ef4444] focus:outline-none"
                  />
                  <button
                    onClick={submitNewResistance}
                    className="bg-[#ef4444]/20 hover:bg-[#ef4444]/30 text-red-400 px-3 rounded text-sm font-medium transition"
                  >
                    添加
                  </button>
                </div>
                <div className="flex flex-wrap gap-2">
                  {resistanceLevels.map((level, i) => (
                    <span
                      key={`r-${i}`}
                      onClick={() => handleRemoveResistance(level)}
                      className="flex items-center gap-1 bg-red-400/10 text-red-400 px-2 py-1 rounded text-xs cursor-pointer hover:bg-red-400/20 font-mono"
                    >
                      {level.toFixed(2)}
                      <XCircle size={12} />
                    </span>
                  ))}
                </div>
              </div>
            </div>

            <div className="p-3 bg-[#1e222d] rounded-lg border border-[#2a2e39] text-xs text-gray-400">
              <p className="mb-1">💡 使用提示</p>
              <ul className="list-disc list-inside space-y-1">
                <li>在 K线图上 右键 可快速添加支撑/阻力位</li>
                <li>点击标签可以删除</li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
