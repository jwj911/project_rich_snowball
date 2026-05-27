import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reportWebVitals } from '@/lib/vitals'

let fetchCalls: Array<{ url: string; body: unknown }> = []
const metricCallbacks: Record<string, Array<(metric: { name: string; value: number; id: string }) => void>> = {}

function mockWebVitals() {
  return {
    onCLS: vi.fn((cb) => { (metricCallbacks['CLS'] ??= []).push(cb) }),
    onINP: vi.fn((cb) => { (metricCallbacks['INP'] ??= []).push(cb) }),
    onFCP: vi.fn((cb) => { (metricCallbacks['FCP'] ??= []).push(cb) }),
    onLCP: vi.fn((cb) => { (metricCallbacks['LCP'] ??= []).push(cb) }),
    onTTFB: vi.fn((cb) => { (metricCallbacks['TTFB'] ??= []).push(cb) }),
  }
}

describe('vitals', () => {
  beforeEach(() => {
    fetchCalls = []
    Object.keys(metricCallbacks).forEach((k) => { metricCallbacks[k] = [] })

    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
      fetchCalls.push({ url, body: init.body ? JSON.parse(init.body as string) : undefined })
      return { ok: true } as Response
    }))
    vi.stubGlobal('navigator', { userAgent: 'test-agent' })
    vi.stubGlobal('location', { href: 'http://test.local/products', pathname: '/products' })

    vi.doMock('web-vitals', () => mockWebVitals())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('registers all 5 web-vitals listeners', async () => {
    const { reportWebVitals: rwv } = await import('@/lib/vitals')
    rwv()

    const webVitals = await import('web-vitals')
    expect(webVitals.onCLS).toHaveBeenCalled()
    expect(webVitals.onINP).toHaveBeenCalled()
    expect(webVitals.onFCP).toHaveBeenCalled()
    expect(webVitals.onLCP).toHaveBeenCalled()
    expect(webVitals.onTTFB).toHaveBeenCalled()
  })

  it('sends POST when metric fires and reportUri is configured', async () => {
    vi.stubGlobal('process', {
      env: {
        NEXT_PUBLIC_SENTRY_REPORT_URI: 'http://test.local/api/log',
        NEXT_PUBLIC_SENTRY_SAMPLE_RATE: '1',
        NEXT_PUBLIC_RELEASE: 'v1.0.0',
        NODE_ENV: 'production',
      },
    })

    const { reportWebVitals: rwv } = await import('@/lib/vitals')
    rwv()

    metricCallbacks['LCP']?.[0]?.({ name: 'LCP', value: 1200, id: 'id-1' })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(fetchCalls).toHaveLength(1)
    const body = fetchCalls[0].body as Record<string, unknown>
    expect(body.type).toBe('web-vitals')
    expect(body.payload).toEqual({ name: 'LCP', value: 1200, id: 'id-1', route: '/products' })
    expect(body.meta).toMatchObject({
      url: 'http://test.local/products',
      ua: 'test-agent',
      release: 'v1.0.0',
      environment: 'production',
    })
    expect(body.meta).toHaveProperty('timestamp')
  })

  it('does not POST when reportUri is absent', async () => {
    vi.stubGlobal('process', {
      env: {
        NEXT_PUBLIC_SENTRY_REPORT_URI: '',
        NEXT_PUBLIC_SENTRY_SAMPLE_RATE: '1',
        NODE_ENV: 'development',
      },
    })

    const { reportWebVitals: rwv } = await import('@/lib/vitals')
    rwv()

    metricCallbacks['FCP']?.[0]?.({ name: 'FCP', value: 300, id: 'id-2' })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(fetchCalls).toHaveLength(0)
  })

  it('respects sampleRate', async () => {
    vi.stubGlobal('process', {
      env: {
        NEXT_PUBLIC_SENTRY_REPORT_URI: 'http://test.local/api/log',
        NEXT_PUBLIC_SENTRY_SAMPLE_RATE: '0',
        NODE_ENV: 'development',
      },
    })

    const { reportWebVitals: rwv } = await import('@/lib/vitals')
    rwv()

    metricCallbacks['CLS']?.[0]?.({ name: 'CLS', value: 0.05, id: 'id-3' })
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(fetchCalls).toHaveLength(0)
  })

  it('does not throw when fetch fails', async () => {
    vi.stubGlobal('process', {
      env: {
        NEXT_PUBLIC_SENTRY_REPORT_URI: 'http://test.local/api/log',
        NEXT_PUBLIC_SENTRY_SAMPLE_RATE: '1',
        NODE_ENV: 'development',
      },
    })

    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('network down')
    }))

    const { reportWebVitals: rwv } = await import('@/lib/vitals')
    rwv()

    expect(() => {
      metricCallbacks['TTFB']?.[0]?.({ name: 'TTFB', value: 50, id: 'id-4' })
    }).not.toThrow()

    await new Promise((resolve) => setTimeout(resolve, 0))
  })
})
