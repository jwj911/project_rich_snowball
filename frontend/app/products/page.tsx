'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import Navbar from '@/components/Navbar'
import { api, Product } from '@/lib/api'
import { TrendingUp, TrendingDown, ArrowUpDown } from 'lucide-react'

export default function ProductsPage() {
  const [products, setProducts] = useState<Product[]>([])
  const [loading, setLoading] = useState(true)
  const [sortBy, setSortBy] = useState<'change_percent' | 'volume' | 'current_price'>('change_percent')
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc')

  useEffect(() => {
    api.getProducts().then(data => {
      setProducts(data)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const sortedProducts = [...products].sort((a, b) => {
    const aVal = a[sortBy] ?? 0
    const bVal = b[sortBy] ?? 0
    return sortOrder === 'desc' ? bVal - aVal : aVal - bVal
  })

  const handleSort = (field: 'change_percent' | 'volume' | 'current_price') => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')
    } else {
      setSortBy(field)
      setSortOrder('desc')
    }
  }

  const SortButton = ({ field, label }: { field: 'change_percent' | 'volume' | 'current_price'; label: string }) => (
    <button
      onClick={() => handleSort(field)}
      className={`flex items-center gap-1 hover:text-white transition-colors ${
        sortBy === field ? 'text-cyan-400' : 'text-slate-400'
      }`}
    >
      {label}
      {sortBy === field && (
        <ArrowUpDown size={14} className={sortOrder === 'asc' ? 'rotate-180' : ''} />
      )}
    </button>
  )

  return (
    <div className="min-h-screen bg-slate-900">
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-white mb-2">品种列表</h1>
          <p className="text-slate-400">查看所有期货品种数据</p>
        </div>

        {loading ? (
          <div className="bg-slate-800 rounded-xl overflow-hidden">
            <div className="animate-pulse p-4 space-y-4">
              {[...Array(10)].map((_, i) => (
                <div key={i} className="h-12 bg-slate-700 rounded"></div>
              ))}
            </div>
          </div>
        ) : (
          <div className="bg-slate-800 rounded-xl overflow-hidden border border-slate-700">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-700">
                  <th className="text-left px-4 py-3 text-sm font-medium text-slate-400">品种</th>
                  <th className="text-right px-4 py-3 text-sm font-medium text-slate-400">
                    <SortButton field="current_price" label="最新价" />
                  </th>
                  <th className="text-right px-4 py-3 text-sm font-medium text-slate-400">
                    <SortButton field="change_percent" label="涨跌幅" />
                  </th>
                  <th className="text-right px-4 py-3 text-sm font-medium text-slate-400">
                    <SortButton field="volume" label="成交量" />
                  </th>
                  <th className="text-right px-4 py-3 text-sm font-medium text-slate-400">操作</th>
                </tr>
              </thead>
              <tbody>
                {sortedProducts.map(product => {
                  const isUp = product.change_percent >= 0
                  return (
                    <tr
                      key={product.id}
                      className="border-b border-slate-700/50 hover:bg-slate-700/30 transition-colors"
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className="text-white font-medium">{product.name}</span>
                          <span className="text-slate-500 text-sm">{product.symbol}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className={`font-mono ${isUp ? 'up' : 'down'}`}>
                          {product.current_price.toLocaleString()}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className={`flex items-center justify-end gap-1 ${isUp ? 'up' : 'down'}`}>
                          {isUp ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                          <span className="font-mono">
                            {isUp ? '+' : ''}{product.change_percent.toFixed(2)}%
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <span className="font-mono text-slate-300">
                          {product.volume?.toLocaleString() ?? '-'}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Link
                          href={`/products/${product.id}`}
                          className="text-cyan-400 hover:text-cyan-300 text-sm transition-colors"
                        >
                          查看详情
                        </Link>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </div>
  )
}
