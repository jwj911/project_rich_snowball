import type { RequestCore } from './request'

export interface DailyCount {
  date: string
  count: number
}

export interface DashboardOverview {
  users: {
    total: number
    today: number
    this_week: number
  }
  comments: {
    total: number
    today: number
  }
  engagement: {
    price_levels: number
    watchlists: number
  }
  market: {
    total_varieties: number
    active_varieties: number
  }
  timestamp: string
}

export interface DashboardActivity {
  new_users: DailyCount[]
  comments: DailyCount[]
  since: string
  timestamp: string
}

export interface CollectionRun {
  job_name: string
  source: string
  status: string
  started_at: string | null
  duration_ms: number | null
  success_count: number | null
  failed_count: number | null
}

export interface DashboardCollection {
  last_24h: {
    total: number
    success: number
    failed: number
    success_rate: number | null
    avg_duration_ms: number | null
  }
  recent_runs: CollectionRun[]
  circuit_breakers: Record<string, unknown>
  timestamp: string
}

export async function getDashboardOverview(core: RequestCore): Promise<DashboardOverview> {
  return core.request<DashboardOverview>('/metrics/dashboard')
}

export async function getDashboardActivity(core: RequestCore): Promise<DashboardActivity> {
  return core.request<DashboardActivity>('/metrics/dashboard/activity')
}

export async function getDashboardCollection(core: RequestCore): Promise<DashboardCollection> {
  return core.request<DashboardCollection>('/metrics/dashboard/collection')
}
