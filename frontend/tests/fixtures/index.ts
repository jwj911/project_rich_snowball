import {
  Comment,
  FutContract,
  KlineData,
  PriceLevel,
  Product,
  RealtimeQuote,
  Variety,
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
