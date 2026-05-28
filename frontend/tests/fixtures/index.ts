import {
  Comment,
  FutContract,
  KlineData,
  PriceLevel,
  Product,
  RealtimeQuote,
  Variety,
  DashboardOverview,
  DashboardActivity,
  DashboardCollection,
} from '@/lib/api'

export function makeProduct(overrides: Partial<Product> = {}): Product {
  return {
    id: 1,
    name: '螺纹钢',
    symbol: 'RB',
    current_price: 3600,
    change_percent: 1.2,
    open_price: 3500,
    high: 3650,
    low: 3490,
    volume: 10000,
    category: '黑色系',
    margin: 12,
    commission: 3,
    updated_at: '2026-05-16T01:00:00.000Z',
    limit_up: 3800,
    limit_down: 3200,
    price_precision: 2,
    ...overrides,
  }
}

export function makeRealtimeQuote(overrides: Partial<RealtimeQuote> = {}): RealtimeQuote {
  return {
    symbol: 'RB',
    current_price: 3600,
    change_percent: 1.2,
    open_price: 3500,
    high: 3620,
    low: 3480,
    volume: 1000,
    updated_at: '2026-05-16T10:00:00',
    limit_up: null,
    limit_down: null,
    ...overrides,
  }
}

export function makeKline(overrides: Partial<KlineData> = {}): KlineData {
  return {
    time: '2026-05-01',
    open: 1,
    high: 2,
    low: 1,
    close: 2,
    volume: 100,
    ...overrides,
  }
}

export function makeComment(overrides: Partial<Comment> = {}): Comment {
  return {
    id: 1,
    product_id: 1,
    product_symbol: 'RB',
    product_name: '螺纹钢',
    variety_id: null,
    variety_symbol: null,
    variety_name: null,
    user_id: 1,
    username: 'trader001',
    content: '观察回踩',
    price_level_id: null,
    created_at: '2026-05-16T01:00:00.000Z',
    ...overrides,
  }
}

export function makeVariety(overrides: Partial<Variety> = {}): Variety {
  return {
    id: 99,
    symbol: 'RB',
    contract_code: 'RB2609',
    name: '螺纹钢',
    exchange: 'SHFE',
    category: '黑色系',
    margin_rate: 12,
    commission: 3,
    tick_size: 1,
    price_precision: 2,
    ...overrides,
  }
}

export function makeFutContract(overrides: Partial<FutContract> = {}): FutContract {
  return {
    id: 12,
    ts_code: 'RB2609.SHF',
    symbol: 'RB2609',
    name: '螺纹钢2609',
    fut_code: 'RB',
    exchange: 'SHFE',
    list_date: null,
    delist_date: null,
    contract_type: null,
    is_active: true,
    ...overrides,
  }
}

export function makePriceLevel(overrides: Partial<PriceLevel> = {}): PriceLevel {
  return {
    id: 1,
    user_id: 1,
    variety_id: 1,
    variety_symbol: 'RB',
    variety_name: '螺纹钢',
    type: 'support',
    price: '3500',
    note: null,
    source: 'manual',
    created_at: '2026-05-16T01:00:00.000Z',
    updated_at: '2026-05-16T01:00:00.000Z',
    ...overrides,
  }
}

export function makeDashboardOverview(overrides: Partial<DashboardOverview> = {}): DashboardOverview {
  return {
    users: { total: 120, today: 3, this_week: 12 },
    comments: { total: 450, today: 8 },
    engagement: { price_levels: 32, watchlists: 18 },
    market: { total_varieties: 56, active_varieties: 42 },
    timestamp: '2026-05-28T09:00:00Z',
    ...overrides,
  }
}

export function makeDashboardActivity(overrides: Partial<DashboardActivity> = {}): DashboardActivity {
  return {
    new_users: [
      { date: '2026-05-22', count: 2 },
      { date: '2026-05-23', count: 1 },
      { date: '2026-05-24', count: 3 },
      { date: '2026-05-25', count: 0 },
      { date: '2026-05-26', count: 2 },
      { date: '2026-05-27', count: 4 },
      { date: '2026-05-28', count: 3 },
    ],
    comments: [
      { date: '2026-05-22', count: 5 },
      { date: '2026-05-23', count: 3 },
      { date: '2026-05-24', count: 8 },
      { date: '2026-05-25', count: 2 },
      { date: '2026-05-26', count: 6 },
      { date: '2026-05-27', count: 4 },
      { date: '2026-05-28', count: 8 },
    ],
    since: '2026-05-22',
    timestamp: '2026-05-28T09:00:00Z',
    ...overrides,
  }
}

export function makeDashboardCollection(overrides: Partial<DashboardCollection> = {}): DashboardCollection {
  return {
    last_24h: {
      total: 48,
      success: 45,
      failed: 3,
      success_rate: 0.9375,
      avg_duration_ms: 1240,
    },
    recent_runs: [
      {
        job_name: 'daily_quotes',
        source: 'tushare',
        status: 'success',
        started_at: '2026-05-28T08:00:00',
        duration_ms: 980,
        success_count: 10,
        failed_count: 0,
      },
      {
        job_name: 'variety_info',
        source: 'internal',
        status: 'success',
        started_at: '2026-05-28T07:30:00',
        duration_ms: 450,
        success_count: 5,
        failed_count: 0,
      },
    ],
    circuit_breakers: { tushare: 'closed', sina: 'closed' },
    timestamp: '2026-05-28T09:00:00Z',
    ...overrides,
  }
}
