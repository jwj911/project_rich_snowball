'use client'

import { useCallback, useMemo, useState } from 'react'
import AppShell from '@/components/layout/AppShell'
import LoginRequired from '@/components/auth/LoginRequired'
import { useAuth } from '@/components/auth/AuthProvider'
import ErrorState from '@/components/ui/ErrorState'
import EmptyState from '@/components/ui/EmptyState'
import { api, type AlertCategory, type AlertEvent, type AlertEventQuery, type AlertSummary, type PriceAlert, type Variety } from '@/lib/api'
import { formatPrice } from '@/lib/format'
import {
  AlertTriangle,
  Bell,
  Check,
  Clock,
  ExternalLink,
  Newspaper,
  Plus,
  ShieldAlert,
  Trash2,
} from 'lucide-react'
import useSWR from 'swr'
import { toast } from 'sonner'

type AlertTab = 'all' | 'news' | 'market' | 'unread'

const TABS: Array<{ key: AlertTab; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'news', label: '新闻预警' },
  { key: 'market', label: '价格预警' },
  { key: 'unread', label: '未读' },
]

export default function AlertsPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth()
  const [activeTab, setActiveTab] = useState<AlertTab>('all')
  const [selectedVarietyId, setSelectedVarietyId] = useState('')
  const [alertType, setAlertType] = useState<'above' | 'below'>('above')
  const [targetPrice, setTargetPrice] = useState('')
  const [creating, setCreating] = useState(false)

  const eventParams = useMemo<AlertEventQuery>(() => {
    if (activeTab === 'news') return { category: 'news', limit: 80 }
    if (activeTab === 'market') return { category: 'market', limit: 80 }
    if (activeTab === 'unread') return { unread_only: true, limit: 80 }
    return { limit: 80 }
  }, [activeTab])

  const {
    data: summary,
    mutate: mutateSummary,
  } = useSWR(isAuthenticated ? 'alert-summary' : null, () => api.getAlertSummary(), {
    revalidateOnFocus: false,
  })

  const {
    data: events,
    error: eventsError,
    isLoading: eventsLoading,
    mutate: mutateEvents,
  } = useSWR(isAuthenticated ? ['alert-events', eventParams] : null, () => api.getAlertEvents(eventParams), {
    revalidateOnFocus: false,
  })

  const { data: varieties } = useSWR(
    isAuthenticated ? 'alert-varieties' : null,
    () => api.getVarieties({ limit: 200 }),
    { revalidateOnFocus: false },
  )

  const {
    data: priceAlerts,
    mutate: mutatePriceAlerts,
  } = useSWR(
    isAuthenticated ? 'active-price-alerts' : null,
    () => api.getPriceAlerts({ triggered: false, limit: 100 }),
    { revalidateOnFocus: false },
  )

  const selectedVariety = useMemo(
    () => varieties?.items.find((item) => String(item.id) === selectedVarietyId),
    [selectedVarietyId, varieties],
  )

  const refreshAlerts = useCallback(() => {
    mutateEvents()
    mutateSummary()
  }, [mutateEvents, mutateSummary])

  const handleCreatePriceAlert = async () => {
    const varietyId = Number(selectedVarietyId)
    const price = Number.parseFloat(targetPrice)
    if (!Number.isFinite(varietyId) || varietyId <= 0) {
      toast.error('请选择品种')
      return
    }
    if (!Number.isFinite(price) || price <= 0) {
      toast.error('请输入有效的目标价格')
      return
    }

    setCreating(true)
    try {
      await api.createPriceAlert({
        variety_id: varietyId,
        alert_type: alertType,
        target_price: targetPrice,
      })
      toast.success('价格预警已创建')
      setTargetPrice('')
      mutatePriceAlerts()
      refreshAlerts()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '创建失败')
    } finally {
      setCreating(false)
    }
  }

  const handleRead = async (eventId: number) => {
    try {
      await api.markAlertEventRead(eventId)
      refreshAlerts()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '标记失败')
    }
  }

  const handleDismiss = async (eventId: number) => {
    try {
      await api.dismissAlertEvent(eventId)
      toast.success('已忽略')
      refreshAlerts()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '操作失败')
    }
  }

  const handleDeletePriceAlert = async (id: number) => {
    if (!confirm('确定删除这条价格预警？')) return
    try {
      await api.deletePriceAlert(id)
      toast.success('价格预警已删除')
      mutatePriceAlerts()
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '删除失败')
    }
  }

  if (authLoading) {
    return (
      <AppShell>
        <StatePanel>正在确认登录状态...</StatePanel>
      </AppShell>
    )
  }

  if (!isAuthenticated) {
    return (
      <AppShell>
        <LoginRequired />
      </AppShell>
    )
  }

  return (
    <AppShell>
      <div className="mx-auto max-w-6xl space-y-5">
        <section className="rounded-lg border border-slate-800 bg-surface p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex items-center gap-3">
              <ShieldAlert size={24} className="text-amber-400" />
              <div>
                <h1 className="text-xl font-bold text-white">预警中心</h1>
                <p className="mt-1 text-sm text-slate-400">
                  汇总重大新闻和已触发的市场价格预警
                </p>
              </div>
            </div>
            <SummaryStrip summary={summary} />
          </div>
        </section>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
          <section className="space-y-4">
            <div className="flex flex-wrap gap-2">
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setActiveTab(tab.key)}
                  className={`rounded-lg border px-3 py-2 text-sm transition ${
                    activeTab === tab.key
                      ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                      : 'border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {eventsError ? (
              <ErrorState
                message={eventsError instanceof Error ? eventsError.message : '加载失败'}
                onRetry={() => refreshAlerts()}
              />
            ) : eventsLoading ? (
              <AlertSkeleton />
            ) : !events || events.length === 0 ? (
              <EmptyState
                icon={Bell}
                title="暂无预警事件"
                description="重大新闻和触发后的价格预警会出现在这里。"
              />
            ) : (
              <div className="space-y-3">
                {events.map((event) => (
                  <AlertEventCard
                    key={event.id}
                    event={event}
                    onRead={handleRead}
                    onDismiss={handleDismiss}
                  />
                ))}
              </div>
            )}
          </section>

          <aside className="space-y-4">
            <PriceAlertCreator
              varieties={varieties?.items ?? []}
              selectedVarietyId={selectedVarietyId}
              selectedVariety={selectedVariety}
              alertType={alertType}
              targetPrice={targetPrice}
              creating={creating}
              onSelectVariety={setSelectedVarietyId}
              onChangeType={setAlertType}
              onChangePrice={setTargetPrice}
              onCreate={handleCreatePriceAlert}
            />
            <ActivePriceAlerts alerts={priceAlerts ?? []} onDelete={handleDeletePriceAlert} />
          </aside>
        </div>
      </div>
    </AppShell>
  )
}

function SummaryStrip({ summary }: { summary?: AlertSummary }) {
  const items = [
    { label: '未读', value: summary?.unread_count ?? 0, icon: Bell },
    { label: '重大新闻', value: summary?.news_count ?? 0, icon: Newspaper },
    { label: '价格预警', value: summary?.market_count ?? 0, icon: AlertTriangle },
  ]

  return (
    <div className="grid grid-cols-3 gap-2 sm:min-w-[360px]">
      {items.map((item) => (
        <div key={item.label} className="rounded-lg border border-slate-800 bg-black/20 px-3 py-2">
          <div className="flex items-center gap-1.5 text-xs text-slate-500">
            <item.icon size={13} />
            {item.label}
          </div>
          <div className="mt-1 text-lg font-semibold text-white">{item.value}</div>
        </div>
      ))}
    </div>
  )
}

function AlertEventCard({
  event,
  onRead,
  onDismiss,
}: {
  event: AlertEvent
  onRead: (id: number) => void
  onDismiss: (id: number) => void
}) {
  const unread = !event.read_at
  const Icon = event.category === 'news' ? Newspaper : AlertTriangle

  return (
    <article className={`rounded-lg border bg-surface p-4 ${unread ? 'border-amber-500/30' : 'border-slate-800'}`}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-300">
              <Icon size={12} />
              {event.category === 'news' ? '新闻' : '价格'}
            </span>
            <SeverityBadge severity={event.severity} />
            {unread && <span className="rounded bg-amber-500/10 px-2 py-0.5 text-xs text-amber-300">未读</span>}
            {event.related_variety_name && (
              <span className="rounded border border-slate-700 px-2 py-0.5 text-xs text-slate-400">
                {event.related_variety_name}
              </span>
            )}
          </div>
          <h2 className="text-base font-semibold text-white">{event.title}</h2>
          {event.summary && <p className="mt-2 text-sm leading-relaxed text-slate-400">{event.summary}</p>}
          <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1">
              <Clock size={12} />
              {formatDateTime(event.triggered_at)}
            </span>
            {event.source_url && (
              <a
                href={event.source_url}
                target={event.source_url.startsWith('http') ? '_blank' : undefined}
                rel={event.source_url.startsWith('http') ? 'noopener noreferrer' : undefined}
                className="inline-flex items-center gap-1 text-slate-400 transition hover:text-amber-300"
              >
                查看来源
                <ExternalLink size={12} />
              </a>
            )}
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          {unread && (
            <button
              type="button"
              onClick={() => onRead(event.id)}
              className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-700 text-slate-400 transition hover:border-slate-500 hover:text-white"
              aria-label="标记已读"
              title="标记已读"
            >
              <Check size={16} />
            </button>
          )}
          <button
            type="button"
            onClick={() => onDismiss(event.id)}
            className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-slate-700 text-slate-400 transition hover:border-red-500/50 hover:text-red-300"
            aria-label="忽略"
            title="忽略"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>
    </article>
  )
}

function SeverityBadge({ severity }: { severity: AlertEvent['severity'] }) {
  const styles = {
    critical: 'border-red-500/40 bg-red-500/10 text-red-300',
    high: 'border-amber-500/40 bg-amber-500/10 text-amber-300',
    medium: 'border-sky-500/40 bg-sky-500/10 text-sky-300',
    low: 'border-slate-600 bg-slate-800 text-slate-300',
  }
  const labels = {
    critical: '紧急',
    high: '重要',
    medium: '中等',
    low: '一般',
  }
  return <span className={`rounded border px-2 py-0.5 text-xs ${styles[severity]}`}>{labels[severity]}</span>
}

function PriceAlertCreator({
  varieties,
  selectedVarietyId,
  selectedVariety,
  alertType,
  targetPrice,
  creating,
  onSelectVariety,
  onChangeType,
  onChangePrice,
  onCreate,
}: {
  varieties: Variety[]
  selectedVarietyId: string
  selectedVariety?: Variety
  alertType: 'above' | 'below'
  targetPrice: string
  creating: boolean
  onSelectVariety: (value: string) => void
  onChangeType: (value: 'above' | 'below') => void
  onChangePrice: (value: string) => void
  onCreate: () => void
}) {
  return (
    <section className="rounded-lg border border-slate-800 bg-surface p-4">
      <div className="mb-3 flex items-center gap-2">
        <Plus size={16} className="text-amber-400" />
        <h2 className="text-sm font-semibold text-white">新建价格预警</h2>
      </div>
      <div className="space-y-3">
        <select
          value={selectedVarietyId}
          onChange={(event) => onSelectVariety(event.target.value)}
          className="w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white outline-none transition focus:border-amber-500/50"
        >
          <option value="">选择品种</option>
          {varieties.map((variety) => (
            <option key={variety.id} value={variety.id}>
              {variety.name} · {variety.symbol}
            </option>
          ))}
        </select>
        <div className="grid grid-cols-2 gap-2">
          {(['above', 'below'] as const).map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => onChangeType(type)}
              className={`rounded-lg border py-2 text-sm transition ${
                alertType === type
                  ? 'border-amber-500/40 bg-amber-500/10 text-amber-300'
                  : 'border-slate-700 text-slate-400 hover:border-slate-500 hover:text-slate-200'
              }`}
            >
              {type === 'above' ? '高于' : '低于'}
            </button>
          ))}
        </div>
        <input
          type="text"
          inputMode="decimal"
          value={targetPrice}
          onChange={(event) => onChangePrice(event.target.value)}
          placeholder={selectedVariety ? `${selectedVariety.name} 目标价` : '目标价格'}
          className="w-full rounded-lg border border-slate-700 bg-black/30 px-3 py-2 text-sm text-white placeholder-slate-500 outline-none transition focus:border-amber-500/50"
        />
        <button
          type="button"
          onClick={onCreate}
          disabled={creating}
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-amber-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <Bell size={15} />
          {creating ? '创建中...' : '创建预警'}
        </button>
      </div>
    </section>
  )
}

function ActivePriceAlerts({
  alerts,
  onDelete,
}: {
  alerts: PriceAlert[]
  onDelete: (id: number) => void
}) {
  return (
    <section className="rounded-lg border border-slate-800 bg-surface p-4">
      <h2 className="mb-3 text-sm font-semibold text-white">未触发价格规则</h2>
      {alerts.length === 0 ? (
        <p className="text-sm text-slate-500">暂无价格预警规则。</p>
      ) : (
        <div className="space-y-2">
          {alerts.map((alert) => (
            <div key={alert.id} className="flex items-center justify-between rounded border border-slate-800 bg-black/20 p-2">
              <div className="min-w-0">
                <div className="truncate text-sm text-slate-200">{alert.variety_name}</div>
                <div className="mt-0.5 text-xs text-slate-500">
                  {alert.alert_type === 'above' ? '高于' : '低于'} {formatPrice(Number(alert.target_price))}
                </div>
              </div>
              <button
                type="button"
                onClick={() => onDelete(alert.id)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-slate-500 transition hover:bg-slate-800 hover:text-red-300"
                aria-label="删除价格预警"
                title="删除"
              >
                <Trash2 size={15} />
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function AlertSkeleton() {
  return (
    <div className="space-y-3">
      {Array.from({ length: 4 }).map((_, index) => (
        <div key={index} className="h-36 animate-pulse rounded-lg border border-slate-800 bg-surface p-4">
          <div className="h-4 w-40 rounded bg-slate-800" />
          <div className="mt-4 h-5 w-3/4 rounded bg-slate-800" />
          <div className="mt-3 h-3 w-full rounded bg-slate-800" />
          <div className="mt-2 h-3 w-2/3 rounded bg-slate-800" />
        </div>
      ))}
    </div>
  )
}

function StatePanel({ children }: { children: string }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-surface p-8 text-center text-slate-400">
      {children}
    </div>
  )
}

function formatDateTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
