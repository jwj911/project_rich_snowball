'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import { api, Product } from '@/lib/api'
import { TrendingUp, TrendingDown, ArrowRight } from 'lucide-react'

export default function HomePage() {
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = () => {
      api.getProducts().then(data => {
        setProducts(data)
        setLoading(false)
      }).catch(() => setLoading(false))
    }
    load()
    const interval = setInterval(load, 30000)
    return () => clearInterval(interval)
  }, [])

  const hotProducts = products.slice(0, 6)

  return (
    <div className="min-h-screen bg-slate-900">
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 py-8">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-white mb-2">热门品种</h1>
          <p className="text-slate-400">点击卡片查看品种详情和社区评论</p>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="bg-slate-800 rounded-xl p-5 h-40 animate-pulse">
                <div className="h-4 bg-slate-700 rounded w-1/3 mb-3"></div>
                <div className="h-8 bg-slate-700 rounded w-2/3 mb-3"></div>
                <div className="h-3 bg-slate-700 rounded w-1/2"></div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {hotProducts.map(product => (
              <Link key={product.id} href={`/products/${product.id}`}>
                <ProductCard product={product} />
              </Link>
            ))}
          </div>
        )}

        <div className="mt-8 text-center">
          <Link
            href="/products"
            className="inline-flex items-center gap-2 text-cyan-400 hover:text-cyan-300 transition-colors"
          >
            查看全部品种
            <ArrowRight size={16} />
          </Link>
        </div>
      </main>
    </div>
  )
}

function ProductCard({ product }: { product: Product }) {
  const isUp = (product.change_percent ?? 0) >= 0

  return (
    <div className="bg-slate-800 rounded-xl p-5 border border-slate-700 hover:border-slate-600 transition-all hover:-translate-y-1 cursor-pointer">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-white font-medium">{product.name}</span>
          <span className="text-slate-500 text-sm">{product.symbol}</span>
        </div>
        {product.category && (
          <span className="text-xs text-slate-500 bg-slate-700 px-2 py-0.5 rounded">
            {product.category}
          </span>
        )}
      </div>

      <div className="mb-3">
        <span className={`text-2xl font-bold font-mono ${isUp ? 'up' : 'down'}`}>
          {product.current_price?.toLocaleString() ?? '--'}
        </span>
      </div>

      <div className="flex items-center justify-between">
        <div className={`flex items-center gap-1 ${isUp ? 'up' : 'down'}`}>
          {isUp ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
          <span className="font-mono text-sm">
            {isUp ? '+' : ''}{(product.change_percent ?? 0).toFixed(2)}%
          </span>
        </div>

        {product.high && product.low && (
          <div className="text-right text-xs text-slate-400">
            <div>最高: <span className="font-mono">{product.high.toLocaleString()}</span></div>
            <div>最低: <span className="font-mono">{product.low.toLocaleString()}</span></div>
          </div>
        )}
      </div>
    </div>
  )
}
