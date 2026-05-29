import { AuthCore } from './auth'
import {
  createComment,
  getProductBySymbol,
  getProducts,
  getProductsPage,
  getUserComments,
} from './products'
import {
  createRealtimeStreamToken,
  getContinuousKline,
  getContractKline,
  getContracts,
  getKline,
  getMainContractKline,
  getMarketStatus,
  getRealtime,
  getRealtimeBatch,
  getVarieties,
  getVariety,
  getVarietyFees,
} from './market'
import {
  getDashboardActivity,
  getDashboardCollection,
  getDashboardOverview,
} from './metrics'
import {
  createPriceLevel,
  createPriceLevelsBatch,
  createWatchlist,
  deletePriceLevel,
  deleteWatchlist,
  getPriceLevels,
  getWatchlists,
  getWorkspace,
  updatePriceLevel,
  updateWatchlist,
} from './workspace'
import type {
  Comment,
  DashboardActivity,
  DashboardCollection,
  DashboardOverview,
  FutContract,
  KlineData,
  MarketStatusResponse,
  PriceLevel,
  Product,
  ProductDetail,
  ProductListResponse,
  ProductQuery,
  RealtimeQuote,
  TokenResponse,
  User,
  Variety,
  VarietyFees,
  Watchlist,
  WorkspaceSummary,
} from './types'

class ApiService extends AuthCore {
  getProducts(options: RequestInit = {}): Promise<Product[]> {
    return getProducts(this, options)
  }

  getProductsPage(params: ProductQuery = {}, options: RequestInit = {}): Promise<ProductListResponse> {
    return getProductsPage(this, params, options)
  }

  getProductBySymbol(symbol: string, options: RequestInit = {}): Promise<ProductDetail> {
    return getProductBySymbol(this, symbol, options)
  }

  createComment(content: string, priceLevelId?: number, varietyId?: number): Promise<Comment> {
    return createComment(this, content, priceLevelId, varietyId)
  }

  getUserComments(username: string): Promise<Comment[]> {
    return getUserComments(this, username)
  }

  getRealtime(symbol: string, options: RequestInit = {}): Promise<RealtimeQuote> {
    return getRealtime(this, symbol, options)
  }

  getRealtimeBatch(symbols: string[]): Promise<{ quotes: RealtimeQuote[]; not_found: string[] }> {
    return getRealtimeBatch(this, symbols)
  }

  createRealtimeStreamToken(options: RequestInit = {}): Promise<{ stream_token: string; expires_in: number }> {
    return createRealtimeStreamToken(this, options)
  }

  getKline(
    symbol: string,
    period: string = '1h',
    limit: number = 100,
    options: RequestInit = {},
  ): Promise<KlineData[]> {
    return getKline(this, symbol, period, limit, options)
  }

  getContinuousKline(
    symbol: string,
    period: string = 'D',
    start?: string,
    end?: string,
    limit: number = 500,
    options: RequestInit = {},
  ): Promise<KlineData[]> {
    return getContinuousKline(this, symbol, period, start, end, limit, options)
  }

  getMainContractKline(
    symbol: string,
    period: string = 'D',
    start?: string,
    end?: string,
    limit: number = 500,
    options: RequestInit = {},
  ): Promise<KlineData[]> {
    return getMainContractKline(this, symbol, period, start, end, limit, options)
  }

  getContracts(
    varietyId: number,
    params?: { activeOnly?: boolean; skip?: number; limit?: number },
    options: RequestInit = {},
  ): Promise<FutContract[]> {
    return getContracts(this, varietyId, params, options)
  }

  getContractKline(
    contractId: number,
    period: string = 'D',
    start?: string,
    end?: string,
    limit: number = 500,
    options: RequestInit = {},
  ): Promise<KlineData[]> {
    return getContractKline(this, contractId, period, start, end, limit, options)
  }

  getVariety(symbol: string, options: RequestInit = {}): Promise<Variety> {
    return getVariety(this, symbol, options)
  }

  getVarieties(
    params?: { category?: string; search?: string; skip?: number; limit?: number },
    options?: RequestInit,
  ): Promise<{ items: Variety[]; total: number }> {
    return getVarieties(this, params, options)
  }

  getPriceLevels(
    varietyId?: number,
    type?: 'support' | 'resistance',
    scope?: 'continuous' | 'main' | 'contract',
    contractId?: number | null,
  ): Promise<PriceLevel[]> {
    return getPriceLevels(this, varietyId, type, scope, contractId)
  }

  createPriceLevel(
    varietyId: number,
    type: 'support' | 'resistance',
    price: string,
    scope?: 'continuous' | 'main' | 'contract',
    contractId?: number | null,
    note?: string,
  ): Promise<PriceLevel> {
    return createPriceLevel(this, varietyId, type, price, scope, contractId, note)
  }

  updatePriceLevel(id: number, updates: { price?: string; note?: string }): Promise<PriceLevel> {
    return updatePriceLevel(this, id, updates)
  }

  deletePriceLevel(id: number): Promise<void> {
    return deletePriceLevel(this, id)
  }

  createPriceLevelsBatch(
    items: Array<{
      variety_id: number
      type: 'support' | 'resistance'
      price: string
      note?: string | null
    }>,
  ): Promise<{
    success: PriceLevel[]
    failed: Array<{ index: number; reason: string }>
    created_count: number
    failed_count: number
  }> {
    return createPriceLevelsBatch(this, items)
  }

  getWatchlists(varietyId?: number): Promise<Watchlist[]> {
    return getWatchlists(this, varietyId)
  }

  createWatchlist(varietyId: number, notes?: string): Promise<Watchlist> {
    return createWatchlist(this, varietyId, notes)
  }

  updateWatchlist(id: number, updates: { notes?: string; is_notified?: boolean }): Promise<Watchlist> {
    return updateWatchlist(this, id, updates)
  }

  deleteWatchlist(id: number): Promise<void> {
    return deleteWatchlist(this, id)
  }

  getWorkspace(options: RequestInit = {}): Promise<WorkspaceSummary> {
    return getWorkspace(this, options)
  }

  getVarietyFees(symbol: string): Promise<VarietyFees> {
    return getVarietyFees(this, symbol)
  }

  getMarketStatus(): Promise<MarketStatusResponse> {
    return getMarketStatus(this)
  }

  getDashboardOverview(): Promise<DashboardOverview> {
    return getDashboardOverview(this)
  }

  getDashboardActivity(): Promise<DashboardActivity> {
    return getDashboardActivity(this)
  }

  getDashboardCollection(): Promise<DashboardCollection> {
    return getDashboardCollection(this)
  }
}

export const api = new ApiService()

export type {
  TokenResponse,
  User,
}
