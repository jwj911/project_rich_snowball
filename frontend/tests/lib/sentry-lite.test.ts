import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { captureException, captureMessage, initSentry } from '@/lib/sentry-lite'

let fetchCalls: Array<{ url: string; body: unknown }> = []

describe('sentry-lite', () => {
  beforeEach(() => {
    fetchCalls = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
      fetchCalls.push({ url, body: init.body ? JSON.parse(init.body as string) : undefined })
      return { ok: true } as Response
    }))
    vi.stubGlobal('navigator', { userAgent: 'test-agent' })
    vi.stubGlobal('location', { href: 'http://test.local/path' })
    initSentry({ enabled: true, reportUri: 'http://test.local/api/log', sampleRate: 1 })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('captureException sends POST when enabled', async () => {
    captureException(new Error('boom'))
    // sendToEndpoint is fire-and-forget; flush microtasks
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(fetchCalls).toHaveLength(1)
    expect(fetchCalls[0].url).toBe('http://test.local/api/log')
    const body = fetchCalls[0].body as Record<string, unknown>
    expect(body.type).toBe('exception')
    const payload = body.payload as Record<string, unknown>
    expect(payload.error).toMatchObject({ name: 'Error', message: 'boom' })
    expect(body.meta).toMatchObject({
      url: 'http://test.local/path',
      ua: 'test-agent',
      environment: 'test',
    })
    expect(body.meta).toHaveProperty('timestamp')
  })

  it('captureException does not POST when enabled=false', async () => {
    initSentry({ enabled: false })
    captureException(new Error('should not send'))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(fetchCalls).toHaveLength(0)
  })

  it('captureMessage sends POST when enabled', async () => {
    captureMessage('hello', 'info')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(fetchCalls).toHaveLength(1)
    const body = fetchCalls[0].body as Record<string, unknown>
    expect(body.type).toBe('message')
    expect(body.level).toBe('info')
    const payload = body.payload as Record<string, unknown>
    expect(payload.message).toBe('hello')
    expect(payload.level).toBe('info')
  })

  it('captureMessage respects sampleRate=0', async () => {
    initSentry({ enabled: true, sampleRate: 0 })
    captureMessage('dropped', 'error')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(fetchCalls).toHaveLength(0)
  })

  it('captureMessage respects sampleRate=0.5 via Math.random', async () => {
    initSentry({ enabled: true, sampleRate: 0.5 })
    vi.stubGlobal('Math', { ...Math, random: vi.fn(() => 0.6) })

    captureMessage('dropped by sample', 'warning')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(fetchCalls).toHaveLength(0)
  })

  it('captureMessage passes sample when Math.random < rate', async () => {
    initSentry({ enabled: true, sampleRate: 0.5 })
    vi.stubGlobal('Math', { ...Math, random: vi.fn(() => 0.3) })

    captureMessage('sampled in', 'error')
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(fetchCalls).toHaveLength(1)
  })

  it('does not throw when fetch fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new Error('network down')
    }))

    expect(() => captureException(new Error('boom'))).not.toThrow()
    expect(() => captureMessage('hello')).not.toThrow()

    await new Promise((resolve) => setTimeout(resolve, 0))
  })

  it('does not report in SSR (window undefined)', async () => {
    vi.stubGlobal('window', undefined)
    vi.stubGlobal('location', undefined)
    vi.stubGlobal('navigator', undefined)

    captureException(new Error('ssr'))
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(fetchCalls).toHaveLength(0)
  })
})
