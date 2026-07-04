'use client'

import { useMemo, useState } from 'react'
import AppShell from '@/components/layout/AppShell'
import LoginRequired from '@/components/auth/LoginRequired'
import { useAuth } from '@/components/auth/AuthProvider'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import EmptyState from '@/components/ui/EmptyState'
import ErrorState from '@/components/ui/ErrorState'
import Input from '@/components/ui/Input'
import MetricCard from '@/components/ui/MetricCard'
import Skeleton from '@/components/ui/Skeleton'
import RefreshStatus from '@/components/activity/RefreshStatus'
import QuoteTable, { QuoteSortField, QuoteSortOrder } from '@/components/market/QuoteTable'
import { Product } from '@/lib/api'
import { formatInteger } from '@/lib/format'
import { useProductListRealtime } from '@/hooks/useProductListRealtime'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { ChevronLeft, ChevronRight, Filter, Search, X } from 'lucide-react'

type DirectionFilter = 'all' | 'up' | 'down'

const EMPTY_PRODUCTS: Product[] = []

const PAGE_SIZE = 20

export default function ProductsPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const [sortBy, setSortBy] = useState<QuoteSortField>('change_percent')
  const [sortOrder, setSortOrder] = useState<QuoteSortOrder>('desc')
  const [searchText, setSearchText] = useState('')
  const debouncedSearchText = useDebouncedValue(searchText, 250)
  const [categoryFilter, setCategoryFilter] = useState('all')
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>('all')
  const [page, setPage] = useState(1)

  const query = useMemo(() => ({
    skip: (page - 1) * PAGE_SIZE,
    limit: PAGE_SIZE,
    search: debouncedSearchText.trim() || undefined,
    category: categoryFilter !== 'all' ? categoryFilter : undefined,
    direction: directionFilter,
    sortBy,
    sortOrder,
  }), [page, debouncedSearchText, categoryFilter, directionFilter, sortBy, sortOrder])

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
        <Card className="p-8 text-center text-gray-800">正在确认登录状态…</Card>
      ) : !isAuthenticated ? (
        <LoginRequired />
      ) : (
        <div className="space-y-5">
          <Card>
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <h1 className="text-heading-24 text-foreground">行情中心</h1>
                <p className="mt-2 text-copy-14 text-gray-800">
                  搜索和筛选期货品种，按价格、涨跌幅或成交量排序。
                </p>
              </div>
              <RefreshStatus heartbeat={heartbeat} onRefresh={refresh} className="lg:min-w-[360px]" />
            </div>

            <div className="mt-5 grid gap-3 sm:grid-cols-4">
              <MetricCard label="品种数" value={formatInteger(total)} />
              <MetricCard label="上涨" value={formatInteger(upCount)} tone="up" />
              <MetricCard label="下跌" value={formatInteger(downCount)} tone="down" />
              <MetricCard label="总成交量" value={formatInteger(totalVolume)} />
            </div>

            <div className="mt-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_180px_180px_auto]">
              <label className="relative block">
                <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-700" />
                <Input
                  type="search"
                  value={searchText}
                  onChange={(event) => handleSearchChange(event.target.value)}
                  placeholder="搜索品种名称、代码或分类"
                  className="pl-9"
                />
              </label>

              <label className="relative block">
                <Filter size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-700" />
                <select
                  value={categoryFilter}
                  onChange={(event) => handleCategoryChange(event.target.value)}
                  className="h-10 w-full appearance-none rounded border border-gray-alpha-400 bg-background pl-9 pr-8 text-label-14 text-foreground outline-none transition hover:border-gray-alpha-500 focus:border-gray-alpha-500 focus:shadow-[0_0_0_2px_#000000,0_0_0_4px_#47a8ff]"
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
                className="h-10 rounded border border-gray-alpha-400 bg-background px-3 text-label-14 text-foreground outline-none transition hover:border-gray-alpha-500 focus:border-gray-alpha-500 focus:shadow-[0_0_0_2px_#000000,0_0_0_4px_#47a8ff]"
              >
                <option value="all">全部涨跌</option>
                <option value="up">上涨品种</option>
                <option value="down">下跌品种</option>
              </select>

              <Button
                type="button"
                variant="secondary"
                onClick={resetFilters}
                disabled={!hasActiveFilter}
                leftIcon={<X size={15} />}
              >
                清除
              </Button>
            </div>
          </Card>

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
                  <Button type="button" onClick={resetFilters}>
                    清除筛选
                  </Button>
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
              <div className="flex flex-wrap items-center justify-between gap-3 text-label-13 text-gray-700">
                <span>
                  共 {total} 个品种 · 当前显示 {(page - 1) * PAGE_SIZE + 1} – {Math.min(page * PAGE_SIZE, total)}
                </span>
                <span>行情数据</span>
              </div>
              <QuoteTable
                products={products}
                sortBy={sortBy}
                sortOrder={sortOrder}
                onSort={handleSort}
              />
              {totalPages > 1 && (
                <div className="flex items-center justify-between gap-3 pt-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={page <= 1}
                    onClick={() => setPage(page - 1)}
                    leftIcon={<ChevronLeft size={16} />}
                  >
                    上一页
                  </Button>
                  <span className="text-label-14 text-gray-800">
                    第 {page} / {totalPages} 页
                  </span>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    disabled={page >= totalPages}
                    onClick={() => setPage(page + 1)}
                    rightIcon={<ChevronRight size={16} />}
                  >
                    下一页
                  </Button>
                </div>
              )}
            </section>
          )}
        </div>
      )}
    </AppShell>
  )
}

function TableSkeleton() {
  return (
    <Card padding="md">
      <div className="space-y-3">
        {Array.from({ length: 8 }).map((_, index) => (
          <Skeleton key={index} className="h-12" />
        ))}
      </div>
    </Card>
  )
}
