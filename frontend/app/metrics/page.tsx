'use client'

import { useEffect, useState } from 'react'
import { useAuth } from '@/components/auth/AuthProvider'
import { useRouter } from 'next/navigation'
import StatCard from '@/components/metrics/StatCard'
import TrendBars from '@/components/metrics/TrendBars'
import { api } from '@/lib/api'
import type { DashboardOverview, DashboardActivity, DashboardCollection } from '@/lib/api'
import {
  Users,
  MessageSquare,
  Layers,
  Bookmark,
  BarChart3,
  Activity,
  Database,
  CheckCircle2,
  XCircle,
  Clock,
} from 'lucide-react'

export default function MetricsPage() {
  const { isAuthenticated } = useAuth()
  const router = useRouter()
  const [overview, setOverview] = useState<DashboardOverview | null>(null)
  const [activity, setActivity] = useState<DashboardActivity | null>(null)
  const [collection, setCollection] = useState<DashboardCollection | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace('/')
      return
    }

    let cancelled = false

    async function load() {
      try {
        setLoading(true)
        const [ov, act, col] = await Promise.all([
          api.getDashboardOverview(),
          api.getDashboardActivity(),
          api.getDashboardCollection(),
        ])
        if (!cancelled) {
          setOverview(ov)
          setActivity(act)
          setCollection(col)
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载失败')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [isAuthenticated, router])

  if (!isAuthenticated) return null

  return (
    <div className="min-h-screen bg-[#0b0f14] p-4 text-slate-200 md:p-8">
      <div className="mx-auto max-w-6xl">
        <div className="mb-6 flex items-center gap-3">
          <BarChart3 size={22} className="text-red-400" />
          <h1 className="text-xl font-bold text-white">运营指标面板</h1>
        </div>

        {loading && (
          <div className="py-20 text-center text-sm text-slate-500">加载中...</div>
        )}

        {error && (
          <div className="rounded-lg border border-red-900/40 bg-red-950/20 p-4 text-sm text-red-300">
            {error}
          </div>
        )}

        {!loading && !error && overview && (
          <>
            {/* 用户与互动 */}
            <section className="mb-8">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
                用户与互动
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard
                  title="总用户数"
                  value={overview.users.total}
                  subtitle={`今日新增 ${overview.users.today}`}
                  icon={<Users size={18} className="text-slate-500" />}
                />
                <StatCard
                  title="本周新增"
                  value={overview.users.this_week}
                  trend="up"
                  icon={<Users size={18} className="text-slate-500" />}
                />
                <StatCard
                  title="评论总数"
                  value={overview.comments.total}
                  subtitle={`今日 ${overview.comments.today}`}
                  icon={<MessageSquare size={18} className="text-slate-500" />}
                />
                <StatCard
                  title="价位标注"
                  value={overview.engagement.price_levels}
                  subtitle={`自选 ${overview.engagement.watchlists}`}
                  icon={<Layers size={18} className="text-slate-500" />}
                />
              </div>
            </section>

            {/* 市场数据 */}
            <section className="mb-8">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
                市场数据
              </h2>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard
                  title="品种总数"
                  value={overview.market.total_varieties}
                  subtitle={`活跃 ${overview.market.active_varieties}`}
                  icon={<Database size={18} className="text-slate-500" />}
                />
                <StatCard
                  title="自选总数"
                  value={overview.engagement.watchlists}
                  icon={<Bookmark size={18} className="text-slate-500" />}
                />
              </div>
            </section>

            {/* 活跃度趋势 */}
            {activity && (
              <section className="mb-8">
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
                  最近 7 天趋势
                </h2>
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <TrendBars data={activity.new_users} label="每日新增用户" colorClass="bg-red-500" />
                  <TrendBars data={activity.comments} label="每日评论数" colorClass="bg-emerald-500" />
                </div>
              </section>
            )}

            {/* 采集健康度 */}
            {collection && (
              <section className="mb-8">
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wider text-slate-500">
                  数据采集健康度（最近 24h）
                </h2>
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <StatCard
                    title="采集任务"
                    value={collection.last_24h.total}
                    subtitle={`成功 ${collection.last_24h.success} / 失败 ${collection.last_24h.failed}`}
                    icon={<Activity size={18} className="text-slate-500" />}
                  />
                  <StatCard
                    title="成功率"
                    value={
                      collection.last_24h.success_rate !== null
                        ? `${(collection.last_24h.success_rate * 100).toFixed(0)}%`
                        : '-'
                    }
                    trend={collection.last_24h.success_rate === 1 ? 'up' : 'neutral'}
                    icon={<CheckCircle2 size={18} className="text-slate-500" />}
                  />
                  <StatCard
                    title="平均耗时"
                    value={
                      collection.last_24h.avg_duration_ms !== null
                        ? `${collection.last_24h.avg_duration_ms}ms`
                        : '-'
                    }
                    icon={<Clock size={18} className="text-slate-500" />}
                  />
                  <StatCard
                    title="熔断器"
                    value={Object.keys(collection.circuit_breakers).length}
                    subtitle="当前监控数据源"
                    icon={<XCircle size={18} className="text-slate-500" />}
                  />
                </div>

                {collection.recent_runs.length > 0 && (
                  <div className="mt-4 overflow-x-auto rounded-xl border border-slate-800 bg-surface">
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr className="border-b border-slate-800 text-xs uppercase text-slate-500">
                          <th className="px-4 py-3">任务</th>
                          <th className="px-4 py-3">来源</th>
                          <th className="px-4 py-3">状态</th>
                          <th className="px-4 py-3">耗时</th>
                          <th className="px-4 py-3">成功/失败</th>
                        </tr>
                      </thead>
                      <tbody>
                        {collection.recent_runs.map((run, idx) => (
                          <tr key={idx} className="border-b border-slate-800/50 text-slate-300">
                            <td className="px-4 py-3 font-medium">{run.job_name}</td>
                            <td className="px-4 py-3">{run.source}</td>
                            <td className="px-4 py-3">
                              <span
                                className={`inline-flex rounded px-2 py-0.5 text-xs font-medium ${
                                  run.status === 'success'
                                    ? 'bg-emerald-950/40 text-emerald-400'
                                    : run.status === 'failed'
                                      ? 'bg-red-950/40 text-red-400'
                                      : 'bg-slate-800 text-slate-400'
                                }`}
                              >
                                {run.status}
                              </span>
                            </td>
                            <td className="px-4 py-3">{run.duration_ms ?? '-'}ms</td>
                            <td className="px-4 py-3">
                              {run.success_count ?? 0} / {run.failed_count ?? 0}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </div>
  )
}
