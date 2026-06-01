'use client'

import { useCallback, useMemo, useState } from 'react'
import AppShell from '@/components/layout/AppShell'
import ErrorState from '@/components/ui/ErrorState'
import EmptyState from '@/components/ui/EmptyState'
import { api, type NewsArticle, type NewsSource } from '@/lib/api'
import { Newspaper, ExternalLink, Search, Rss, Clock, Filter } from 'lucide-react'
import useSWR from 'swr'

export default function NewsPage() {
  const [selectedSource, setSelectedSource] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')

  const {
    data: sources,
    error: sourcesError,
    isLoading: sourcesLoading,
    mutate: mutateSources,
  } = useSWR('news-sources', () => api.getNewsSources(), { revalidateOnFocus: false })

  const {
    data: articles,
    error: articlesError,
    isLoading: articlesLoading,
    mutate: mutateArticles,
  } = useSWR(
    ['news-articles', selectedSource, searchQuery],
    () =>
      api.getNewsArticles({
        source_id: selectedSource ?? undefined,
        q: searchQuery || undefined,
        limit: 50,
      }),
    { revalidateOnFocus: false },
  )

  const sourceMap = useMemo(() => {
    const map = new Map<number, NewsSource>()
    sources?.forEach((s) => map.set(s.id, s))
    return map
  }, [sources])

  const loading = sourcesLoading || articlesLoading
  const error = sourcesError || articlesError

  const handleSourceFilter = useCallback(
    (sourceId: number | null) => {
      setSelectedSource(sourceId)
    },
    [],
  )

  return (
    <AppShell>
      <div className="mx-auto max-w-4xl space-y-5">
        {/* Header */}
        <section className="rounded-lg border border-slate-800 bg-surface p-5">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="flex items-center gap-3">
              <Newspaper size={22} className="text-red-400" />
              <div>
                <h1 className="text-xl font-bold text-white">新闻资讯</h1>
                <p className="mt-1 text-sm text-slate-400">
                  聚合市场新闻与行业动态
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Rss size={14} className="text-slate-500" />
              <span className="text-xs text-slate-500">
                {sources?.length ?? 0} 个数据源
              </span>
            </div>
          </div>

          {/* Search */}
          <div className="mt-4">
            <div className="relative">
              <Search
                size={16}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-500"
              />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="搜索新闻标题..."
                className="w-full rounded-lg border border-slate-700 bg-black/30 py-2.5 pl-10 pr-4 text-sm text-white placeholder-slate-500 outline-none transition focus:border-red-500/50"
              />
            </div>
          </div>
        </section>

        {/* Source filters */}
        {sources && sources.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <Filter size={14} className="text-slate-500" />
            <button
              type="button"
              onClick={() => handleSourceFilter(null)}
              className={`rounded-full px-3 py-1 text-xs transition ${
                selectedSource === null
                  ? 'bg-red-600/20 text-red-300 border border-red-500/30'
                  : 'border border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
              }`}
            >
              全部
            </button>
            {sources.map((source) => (
              <button
                key={source.id}
                type="button"
                onClick={() => handleSourceFilter(source.id)}
                className={`rounded-full px-3 py-1 text-xs transition ${
                  selectedSource === source.id
                    ? 'bg-red-600/20 text-red-300 border border-red-500/30'
                    : 'border border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                }`}
              >
                {source.name}
              </button>
            ))}
          </div>
        )}

        {error ? (
          <ErrorState
            message={error instanceof Error ? error.message : '加载失败'}
            onRetry={() => {
              mutateSources()
              mutateArticles()
            }}
          />
        ) : loading ? (
          <NewsSkeleton />
        ) : !articles || articles.length === 0 ? (
          <EmptyState
            icon={Newspaper}
            title="暂无新闻"
            description="当前没有符合条件的新闻资讯。"
          />
        ) : (
          <section className="space-y-3">
            {articles.map((article) => (
              <ArticleCard
                key={article.id}
                article={article}
                source={sourceMap.get(article.source_id)}
              />
            ))}
          </section>
        )}
      </div>
    </AppShell>
  )
}

function ArticleCard({
  article,
  source,
}: {
  article: NewsArticle
  source?: NewsSource
}) {
  return (
    <a
      href={article.url}
      target="_blank"
      rel="noopener noreferrer"
      className="group block rounded-lg border border-slate-800 bg-surface p-4 transition hover:border-red-800/50 hover:bg-[#121b24]"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-medium text-white group-hover:text-red-300 transition">
            {article.title}
          </h3>
          {article.summary && (
            <p className="mt-1.5 text-sm leading-relaxed text-slate-400 line-clamp-2">
              {article.summary}
            </p>
          )}
          <div className="mt-2.5 flex flex-wrap items-center gap-3 text-xs text-slate-500">
            {source && (
              <span className="rounded border border-slate-700 px-1.5 py-0.5">
                {source.name}
              </span>
            )}
            {article.published_at && (
              <span className="flex items-center gap-1">
                <Clock size={12} />
                {formatRelativeTime(article.published_at)}
              </span>
            )}
          </div>
        </div>
        <ExternalLink
          size={16}
          className="mt-0.5 shrink-0 text-slate-600 group-hover:text-red-400 transition"
        />
      </div>
    </a>
  )
}

function formatRelativeTime(iso: string): string {
  const date = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)

  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin} 分钟前`
  if (diffHour < 24) return `${diffHour} 小时前`
  if (diffDay < 7) return `${diffDay} 天前`
  return date.toLocaleDateString('zh-CN')
}

function NewsSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="h-28 animate-pulse rounded-lg border border-slate-800 bg-surface p-4"
        >
          <div className="h-4 w-3/4 rounded bg-slate-800" />
          <div className="mt-3 h-3 w-full rounded bg-slate-800" />
          <div className="mt-2 h-3 w-1/2 rounded bg-slate-800" />
        </div>
      ))}
    </div>
  )
}
