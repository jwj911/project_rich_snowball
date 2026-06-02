'use client'

import { useCallback, useMemo, useState } from 'react'
import AppShell from '@/components/layout/AppShell'
import ErrorState from '@/components/ui/ErrorState'
import EmptyState from '@/components/ui/EmptyState'
import { api, type NewsArticle, type NewsSource } from '@/lib/api'
import {
  Newspaper,
  ExternalLink,
  Search,
  Rss,
  Clock,
  Filter,
  Sparkles,
  ChevronDown,
  ChevronUp,
  Plus,
  X,
  Trash2,
  Settings,
  Loader2,
} from 'lucide-react'
import useSWR from 'swr'
import { toast } from 'sonner'

export default function NewsPage() {
  const [selectedSource, setSelectedSource] = useState<number | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [showSourceModal, setShowSourceModal] = useState(false)

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
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setShowSourceModal(true)}
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
              >
                <Settings size={13} />
                管理源
              </button>
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
                onSummarized={() => mutateArticles()}
              />
            ))}
          </section>
        )}
      </div>

      {showSourceModal && (
        <SourceManagerModal
          sources={sources ?? []}
          onClose={() => setShowSourceModal(false)}
          onChange={() => mutateSources()}
        />
      )}
    </AppShell>
  )
}

function ArticleCard({
  article,
  source,
  onSummarized,
}: {
  article: NewsArticle
  source?: NewsSource
  onSummarized: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const [summarizing, setSummarizing] = useState(false)

  const handleSummarize = async () => {
    setSummarizing(true)
    try {
      await api.summarizeArticle(article.id)
      toast.success('AI 解读已生成')
      onSummarized()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '生成失败')
    } finally {
      setSummarizing(false)
    }
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-surface p-4 transition hover:border-red-800/50 hover:bg-[#121b24]">
      <a
        href={article.url}
        target="_blank"
        rel="noopener noreferrer"
        className="group block"
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

      {/* AI Summary */}
      {article.ai_summary ? (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="inline-flex items-center gap-1.5 text-xs text-amber-400 transition hover:text-amber-300"
          >
            <Sparkles size={12} />
            AI 解读
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </button>
          {expanded && (
            <div className="mt-2 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-sm leading-relaxed text-slate-300">
              {article.ai_summary}
            </div>
          )}
        </div>
      ) : (
        <div className="mt-3">
          <button
            type="button"
            onClick={handleSummarize}
            disabled={summarizing}
            className="inline-flex items-center gap-1.5 text-xs text-slate-500 transition hover:text-amber-400 disabled:opacity-50"
          >
            <Sparkles size={12} />
            {summarizing ? '生成中...' : '生成 AI 解读'}
          </button>
        </div>
      )}
    </div>
  )
}

function SourceManagerModal({
  sources,
  onClose,
  onChange,
}: {
  sources: NewsSource[]
  onClose: () => void
  onChange: () => void
}) {
  const [showAddForm, setShowAddForm] = useState(false)
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [category, setCategory] = useState('')

  const handleAdd = async () => {
    if (!name.trim() || !url.trim()) {
      toast.error('名称和 URL 不能为空')
      return
    }
    try {
      await api.createNewsSource({ name: name.trim(), url: url.trim(), category: category.trim() || null })
      toast.success('源已添加')
      setName('')
      setUrl('')
      setCategory('')
      setShowAddForm(false)
      onChange()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '添加失败')
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除这个 RSS 源？')) return
    try {
      await api.deleteNewsSource(id)
      toast.success('已删除')
      onChange()
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '删除失败')
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-xl border border-slate-700 bg-[#0f172a] shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-800 px-5 py-4">
          <h2 className="text-base font-semibold text-white">管理 RSS 源</h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 transition hover:bg-slate-800 hover:text-white"
          >
            <X size={18} />
          </button>
        </div>

        <div className="max-h-[60vh] overflow-y-auto px-5 py-4">
          {/* Source list */}
          <div className="space-y-2">
            {sources.map((source) => (
              <div
                key={source.id}
                className="flex items-center justify-between rounded-lg border border-slate-800 bg-black/20 px-3 py-2"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-sm text-white">{source.name}</span>
                    {source.is_builtin && (
                      <span className="rounded bg-slate-700 px-1.5 py-0.5 text-[10px] text-slate-300">
                        内置
                      </span>
                    )}
                  </div>
                  <p className="mt-0.5 truncate text-xs text-slate-500">{source.url}</p>
                </div>
                {!source.is_builtin && (
                  <button
                    type="button"
                    onClick={() => handleDelete(source.id)}
                    className="ml-2 rounded p-1 text-slate-500 transition hover:bg-slate-800 hover:text-red-400"
                  >
                    <Trash2 size={14} />
                  </button>
                )}
              </div>
            ))}
          </div>

          {/* Add form */}
          {showAddForm ? (
            <div className="mt-4 space-y-3">
              <div>
                <label className="mb-1 block text-xs text-slate-400">名称</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="如：新浪财经期货"
                  className="w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white outline-none transition focus:border-red-500/50"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-400">RSS URL</label>
                <input
                  type="text"
                  value={url}
                  onChange={(e) => setUrl(e.target.value)}
                  placeholder="https://example.com/rss.xml"
                  className="w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white outline-none transition focus:border-red-500/50"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-slate-400">分类（可选）</label>
                <input
                  type="text"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  placeholder="如：综合财经"
                  className="w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white outline-none transition focus:border-red-500/50"
                />
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setShowAddForm(false)}
                  className="flex-1 rounded-lg border border-slate-700 py-2 text-xs text-slate-300 transition hover:border-slate-500"
                >
                  取消
                </button>
                <button
                  type="button"
                  onClick={handleAdd}
                  className="flex-1 rounded-lg bg-red-600 py-2 text-xs font-medium text-white transition hover:bg-red-500"
                >
                  添加
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setShowAddForm(true)}
              className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-dashed border-slate-700 py-2.5 text-xs text-slate-400 transition hover:border-slate-500 hover:text-slate-200"
            >
              <Plus size={14} />
              添加自定义 RSS 源
            </button>
          )}
        </div>
      </div>
    </div>
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
