import { api, RealtimeQuote } from '@/lib/api'
import { captureMessage } from '@/lib/sentry-lite'
import { MARKET } from '@/lib/constants'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8200'
const SSE_RETRY_DELAY_MS = MARKET.SSE_RETRY_DELAY_MS
const POLL_INTERVAL_MS = MARKET.SSE_FALLBACK_INTERVAL_MS
const BATCH_INTERVAL_MS = MARKET.BATCH_INTERVAL_MS
const MAX_RECONNECT_DELAY = MARKET.MAX_RECONNECT_DELAY

export interface RealtimeStoreState {
  quotes: Map<string, RealtimeQuote>
  source: 'sse' | 'polling' | null
  error: string | null
  loading: boolean
}

type SubscriberCallback = (state: RealtimeStoreState) => void

interface Subscriber {
  symbols: Set<string>
  callback: SubscriberCallback
}

class RealtimeStore {
  private es: EventSource | null = null
  private subscribers: Subscriber[] = []
  private batchQueue: RealtimeQuote[] = []
  private batchTimer: number | null = null
  private _source: 'sse' | 'polling' | null = null
  private _error: string | null = null
  private _loading = false
  private reconnectAttempts = 0
  private reconnectTimer: number | null = null
  private pollInterval: number | null = null
  private activeSymbols: string[] = []
  private visibilityHandler: (() => void) | null = null
  private _quotes = new Map<string, RealtimeQuote>()

  private get allSymbols(): string[] {
    const set = new Set<string>()
    this.subscribers.forEach((s) => {
      s.symbols.forEach((sym) => set.add(sym))
    })
    return Array.from(set)
  }

  private symbolsChanged(next: string[]): boolean {
    if (next.length !== this.activeSymbols.length) return true
    for (let i = 0; i < next.length; i++) {
      if (next[i] !== this.activeSymbols[i]) return true
    }
    return false
  }

  subscribe(symbols: string[], callback: SubscriberCallback): () => void {
    const subscriber: Subscriber = {
      symbols: new Set(symbols),
      callback,
    }
    this.subscribers.push(subscriber)

    // 新 subscriber 立即收到已有 quote 的快照
    const snapshot = new Map<string, RealtimeQuote>()
    symbols.forEach((sym) => {
      const q = this._quotes.get(sym)
      if (q) snapshot.set(sym, q)
    })

    callback({
      quotes: snapshot,
      source: this._source,
      error: this._error,
      loading: this._loading,
    })

    this.reconnectIfNeeded()

    return () => {
      const idx = this.subscribers.indexOf(subscriber)
      if (idx >= 0) {
        this.subscribers.splice(idx, 1)
      }
      if (this.subscribers.length === 0) {
        this.disconnect()
      } else {
        this.reconnectIfNeeded()
      }
    }
  }

  private reconnectIfNeeded(): void {
    const nextSymbols = this.allSymbols.sort()
    if (!this.symbolsChanged(nextSymbols)) return

    this.disconnectInternals()
    this.activeSymbols = nextSymbols
    if (nextSymbols.length > 0) {
      this.connect()
    }
  }

  private buildSseUrl(symbols: string[]): string {
    const params = new URLSearchParams()
    // 当品种数过多时，不传 symbols 参数，后端自动订阅全部活跃品种，
    // 避免 URL 超过浏览器/服务器长度限制（通常 2048 字符）。
    const MAX_SSE_URL_SYMBOLS = 30
    if (symbols.length > 0 && symbols.length <= MAX_SSE_URL_SYMBOLS) {
      symbols.forEach((s) => { params.append('symbols', s) })
    }
    return `${API_BASE}/api/realtime/stream?${params.toString()}`
  }

  private connect(): void {
    const token = api.getToken()
    if (!token) {
      this.startPolling()
      return
    }

    try {
      this.es = new EventSource(this.buildSseUrl(this.activeSymbols), {
        withCredentials: true,
      })

      this.es.onopen = () => {
        this.reconnectAttempts = 0
        this._source = 'sse'
        this._error = null
        this.stopPolling()
        this.notifyAll()
      }

      this.es.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          const quotes: RealtimeQuote[] = data.quotes ?? []
          this.enqueue(quotes)
        } catch {
          captureMessage('SSE 消息解析失败', 'error')
        }
      }

      this.es.onerror = () => {
        this.es?.close()
        this.es = null
        this._source = 'polling'
        this._error = 'SSE 连接失败，已降级到轮询'
        this.notifyAll()
        this.startPolling()
        this.scheduleReconnect()
      }
    } catch {
      this._source = 'polling'
      this.startPolling()
    }

    if (!this.visibilityHandler) {
      this.visibilityHandler = () => this.handleVisibilityChange()
      document.addEventListener('visibilitychange', this.visibilityHandler)
    }
  }

  private disconnect(): void {
    this.disconnectInternals()
    this.subscribers = []
    this.activeSymbols = []
    this._source = null
    this._error = null
    this._loading = false
    this.reconnectAttempts = 0
    this._quotes.clear()
  }

  private disconnectInternals(): void {
    this.stopPolling()
    this.clearReconnectTimer()
    this.clearBatchTimer()
    if (this.es) {
      this.es.close()
      this.es = null
    }
    if (this.visibilityHandler) {
      document.removeEventListener('visibilitychange', this.visibilityHandler)
      this.visibilityHandler = null
    }
  }

  private startPolling(): void {
    if (this.pollInterval) return
    this._loading = true
    this.notifyAll()
    this.poll()
    this.pollInterval = window.setInterval(() => this.poll(), POLL_INTERVAL_MS)
  }

  private stopPolling(): void {
    if (this.pollInterval) {
      window.clearInterval(this.pollInterval)
      this.pollInterval = null
    }
  }

  private async poll(): Promise<void> {
    if (this.activeSymbols.length === 0) return
    try {
      const { quotes } = await api.getRealtimeBatch(this.activeSymbols)
      this._loading = false
      this._error = null
      quotes.forEach((q) => { this._quotes.set(q.symbol, q) })
      this.enqueue(quotes)
    } catch (err) {
      this._error = err instanceof Error ? err.message : '轮询失败'
      this._loading = false
      this.notifyAll()
    }
  }

  private scheduleReconnect(): void {
    this.reconnectAttempts += 1
    const delay = Math.min(
      SSE_RETRY_DELAY_MS * 2 ** (this.reconnectAttempts - 1),
      MAX_RECONNECT_DELAY,
    )
    this.clearReconnectTimer()
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null
      if (this.subscribers.length > 0) {
        this.connect()
      }
    }, delay)
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer) {
      window.clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private handleVisibilityChange(): void {
    if (document.hidden) {
      this.es?.close()
      this.es = null
    } else if (api.getToken() && !this.es && this.subscribers.length > 0) {
      this.reconnectAttempts = 0
      this.clearReconnectTimer()
      this.connect()
    }
  }

  private enqueue(quotes: RealtimeQuote[]): void {
    quotes.forEach((q) => { this.batchQueue.push(q) })
    if (!this.batchTimer) {
      this.batchTimer = window.setTimeout(() => this.flushBatch(), BATCH_INTERVAL_MS)
    }
  }

  private flushBatch(): void {
    this.batchTimer = null
    if (this.batchQueue.length === 0) return

    const batchMap = new Map<string, RealtimeQuote>()
    this.batchQueue.forEach((q) => {
      batchMap.set(q.symbol, q)
      this._quotes.set(q.symbol, q)
    })
    this.batchQueue = []
    this.notifyAll(batchMap)
  }

  private clearBatchTimer(): void {
    if (this.batchTimer) {
      window.clearTimeout(this.batchTimer)
      this.batchTimer = null
    }
    this.batchQueue = []
  }

  private notifyAll(quotes?: Map<string, RealtimeQuote>): void {
    this.subscribers.forEach((subscriber) => {
      const filtered = new Map<string, RealtimeQuote>()
      if (quotes) {
        quotes.forEach((quote, symbol) => {
          if (subscriber.symbols.has(symbol)) {
            filtered.set(symbol, quote)
          }
        })
      }
      subscriber.callback({
        quotes: filtered,
        source: this._source,
        error: this._error,
        loading: this._loading,
      })
    })
  }

  /** 仅用于测试。 */
  resetForTest(): void {
    this.disconnect()
  }

  /** 仅用于测试：获取内部 quotes 缓存。 */
  getQuotesForTest(): Map<string, RealtimeQuote> {
    return new Map(this._quotes)
  }
}

export const realtimeStore = new RealtimeStore()
