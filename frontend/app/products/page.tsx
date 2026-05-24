'use client'

import { useCallback, useMemo, useState } from 'react'
import AppShell from '@/components/layout/AppShell'
import LoginRequired from '@/components/auth/LoginRequired'
import { useAuth } from '@/components/auth/AuthProvider'
import EmptyState from '@/components/ui/EmptyState'
import ErrorState from '@/components/ui/ErrorState'
import RefreshStatus from '@/components/activity/RefreshStatus'
import QuoteTable, { QuoteSortField, QuoteSortOrder } from '@/components/market/QuoteTable'
import { api, Product } from '@/lib/api'
import { formatInteger } from '@/lib/format'
import { useProductListRealtime } from '@/hooks/useProductListRealtime'
import { Filter, Search, X } from 'lucide-react'

type DirectionFilter = 'all' | 'up' | 'down'

const EMPTY_PRODUCTS: Product[] = []

const PAGE_SIZE = 20

export default function ProductsPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const [sortBy, setSortBy] = useState<QuoteSortField>('change_percent')
  const [sortOrder, setSortOrder] = useState<QuoteSortOrder>('desc')
  const [searchText, setSearchText] = useState('')
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>('all')
  const [page, setPage] = useState(1)

  const query = useMemo(() => ({
    skip: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
    search: searchText.trim() || undefined,
    category: categoryFilter !== 'all' ? categoryFilter : undefined,
    direction: directionFilter,
    sortBy,
    sortOrder,
  }), [page, searchText, categoryFilter, directionFilter, sortBy, sortOrder])

  const {
    products,
    total,
    totalVolume,
    upCount,
    downCount,
    categories,
    loading,
    error,
    heartbeat,
    refresh,
  } = useProductListRealtime(!authLoading && isAuthenticated, query)

  const hasActiveFilter = searchText.trim() !== '' || categoryFilter !== 'all' || directionFilter !== 'all'
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const handleSort = (field: QuoteSortField) => {
    if (sortBy === field) {
      setSortOrder(sortOrder === 'desc' ? 'asc' : 'desc')
    } else {
      setSortBy(field)
      setSortOrder('desc')
    }
    setPage(1)
  }

  const handleSearchChange = (value: string) => {
    setSearchText(value)
    setPage(1)
  }

  const handleCategoryChange = (value: string) => {
    setCategoryFilter(value)
    setPage(1)
  }

  const handleDirectionChange = (value: DirectionFilter) => {
    setDirectionFilter(value)
    setPage(1)
  }

  const resetFilters = () => {
    setSearchText('')
    setCategoryFilter('all')
    setDirectionFilter('all')
    setPage(1)
  }

  return (
    <AppShell>
      {authLoading ? (
        <div className="rounded-lg border border-slate-800 bg-[#10161d] p-8 text-center text-slate-400">
          正在确认登录状态...
        </div>
      ) : !isAuthenticated ? (
        <LoginRequired />
      ) : (
        <div className="space-y-5">
          <section className="rounded-lg border border-slate-800 bg-[#10161d] p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h1 className="text-2xl font-bold text-white">行情中心</h1>
                <p className="mt-2 text-sm leading-6 text-slate-400">
                  搜索和筛选期货品种，按价格、涨跌幅或成交量排序。
                </p>
              </div>
              <RefreshStatus heartbeat={heartbeat} onRefresh={refresh} className="lg:min-w-[360px]" />
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <Metric label="品种数" value={formatInteger(total)} />
              <Metric label="上涨" value={formatInteger(upCount)} tone="up" />
              <Metric label="下跌" value={formatInteger(downCount)} tone="down" />
              <Metric label="总成交量" value={formatInteger(totalVolume)} />
            </div>

            <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px_180px_auto]">
              <label className="relative block">
                <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <input
                  type="search"
                  value={searchText}
                  onChange={(event) => handleSearchChange(event.target.value)}
                  placeholder="搜索品种名称、代码或分类"
                  className="h-10 w-full rounded-lg border border-slate-700 bg-black/30 pl-9 pr-3 text-sm text-white outline-none transition placeholder:text-slate-600 focus:border-red-800"
                />
              </label>

              <label className="relative block">
                <Filter size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-500" />
                <select
                  value={categoryFilter}
                  onChange={(event) => handleCategoryChange(event.target.value)}
                  className="h-10 w-full appearance-none rounded-lg border border-slate-700 bg-black/30 pl-9 pr-3 text-sm text-white outline-none transition focus:border-red-800"
                >
                  <option value="all">全部分类</option>
                  {categories.map((category) => (
                    <option key={category} value={category}>{category}</option>
                  ))}
                </select>
              </label>

              <label htmlFor="direction-filter" className="sr-only">涨跌方向筛选</label>
              <select
                id="direction-filter"
                value={directionFilter}
                onChange={(event) => handleDirectionChange(event.target.value as DirectionFilter)}
                className="h-10 rounded-lg border border-slate-700 bg-black/30 px-3 text-sm text-white outline-none transition focus:border-red-800"
              >
                <option value="all">全部涨跌</option>
                <option value="up">上涨品种</option>
                <option value="down">下跌品种</option>
              </select>

              <button
                type="button"
                onClick={resetFilters}
                disabled={!hasActiveFilter}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-slate-700 px-3 text-sm text-slate-300 transition hover:border-red-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
              >
                <X size={15} />
                清除
              </button>
            </div>
          </section>

          {loading ? (
            <TableSkeleton />
          ) : error ? (
            <ErrorState message={error} onRetry={refresh} />
          ) : total === 0 ? (
            hasActiveFilter ? (
              <EmptyState
                icon={Search}
                title="没有匹配的品种"
                description="调整搜索词或筛选条件后再试。"
                action={
                  <button
                    type="button"
                    onClick={resetFilters}
                    className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-700"
                  >
                    清除筛选
                  </button>
                }
              />
            ) : (
              <EmptyState
                icon={Search}
                title="暂无品种数据"
                description="当前没有可展示的期货品种，请稍后重试。"
              />
            )
          ) : (
            <section className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-slate-500">
                <span>
                  共 {total} 个品种 · 当前显示 {(page - 1) * PAGE_SIZE + 1} – {Math.min(page * PAGE_SIZE, total)}
                </span>
                <span>每 30 秒自动刷新</span>
              </div>
              <QuoteTable
                products={products}
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSort}
              />
              {totalPages > 1 && (
                <div className="flex items-center justify-between gap-3 pt-2">
                  <button
                    type="button"
                    disabled={page <= 1}
                    onClick={() => setPage(page - 1)}
                    className="inline-flex h-9 items-center rounded-lg border border-slate-700 px-3 text-sm text-slate-300 transition hover:border-red-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    上一页
                  </button>
                  <span className="text-sm text-slate-400">
                    第 {page} / {totalPages} 页
                  </span>
                  <button
                    type="button"
                    disabled={page >= totalPages}
                    onClick={() => setPage(page + 1)}
                    className="inline-flex h-9 items-center rounded-lg border border-slate-700 px-3 text-sm text-slate-300 transition hover:border-red-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    下一页
                  </button>
                </div>
              )}
            </section>
          )}
        </div>
      )}
    </AppShell>
  )
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'up' | 'down' }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-black/30 p-3">
      <div className="text-xs text-slate-500">{label}</div>
      <div className={`mt-2 font-mono text-xl font-semibold ${tone ?? 'text-white'}`}>{value}</div>
    </div>
  )
}

function TableSkeleton() {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-800 bg-[#10161d] p-4">
      <div className="space-y-3">
        {Array.from({ length: 8 }).map((_, index) => (
          <div key={index} className="h-12 animate-pulse rounded bg-slate-800" />
        ))}
      </div>
    </div>
  )
}
