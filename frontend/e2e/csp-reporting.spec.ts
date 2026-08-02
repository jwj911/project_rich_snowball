import { expect, Page, Request, Route, test } from '@playwright/test'

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || 'http://127.0.0.1:8401'
const API_ORIGIN = new URL(API_BASE).origin
const ACCESS_TOKEN_KEY = 'futures_access_token'
const ACCESS_COOKIE_NAME = 'access_token'
const REFRESH_COOKIE_NAME = 'refresh_token'

async function login(page: Page) {
  await page.goto('/')
  await page.getByRole('navigation').getByRole('button', { name: '登录' }).click()
  await page.getByLabel('用户名').fill('trader001')
  await page.getByLabel('密码').fill('password123')
  await page.getByRole('dialog', { name: '登录' }).getByRole('button', { name: '登录' }).click()
  await expect(page.getByRole('heading', { name: '行情工作台' })).toBeVisible({ timeout: 15000 })
}

async function getAuthCookieState(page: Page) {
  const cookies = await page.context().cookies(`${API_BASE}/api/auth/refresh`)
  return {
    hasHttpOnlyAccessCookie: cookies.some(
      (cookie) => cookie.name === ACCESS_COOKIE_NAME && cookie.httpOnly,
    ),
    hasHttpOnlyRefreshCookie: cookies.some(
      (cookie) => cookie.name === REFRESH_COOKIE_NAME && cookie.httpOnly,
    ),
  }
}

async function requestHasCookie(request: Request, cookieName: string) {
  const cookieHeader = (await request.allHeaders()).cookie ?? ''
  return cookieHeader
    .split(';')
    .some((cookie) => cookie.trim().startsWith(`${cookieName}=`))
}

async function requestHasBearerAuthorization(request: Request) {
  const authorization = (await request.allHeaders()).authorization
  return authorization?.startsWith('Bearer ') === true
}

test.describe.serial('R9 CSP Report-Only 契约', () => {
  test('页面同时发送强制与 Report-Only CSP', async ({ page }) => {
    const response = await page.goto('/')

    expect(response).not.toBeNull()
    const enforced = await response!.headerValue('content-security-policy')
    const reportOnly = await response!.headerValue('content-security-policy-report-only')
    const reportingEndpoints = await response!.headerValue('reporting-endpoints')

    expect(enforced).toBe([
      "default-src 'self'",
      "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' blob: data:",
      `connect-src 'self' ${API_BASE}`,
      "font-src 'self'",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join('; '))
    expect(reportOnly).not.toBeNull()
    const reportOnlyDirectives = new Map(
      reportOnly!.split(';').map((directive) => {
        const [name, ...values] = directive.trim().split(/\s+/)
        return [name, values] as const
      }),
    )
    expect(reportOnlyDirectives.get('script-src')).toEqual(["'self'"])
    expect(reportOnlyDirectives.get('style-src')).toContain("'unsafe-inline'")
    expect(reportOnly).toContain(`report-uri ${API_BASE}/api/log/csp-report`)
    expect(reportOnly).toContain('report-to csp-report')
    expect(reportingEndpoints).toBe(`csp-report="${API_BASE}/api/log/csp-report"`)
  })

  test('后端安全接收 legacy 与 Reporting API synthetic 报告', async ({ request }) => {
    const legacyResponse = await request.post(`${API_BASE}/api/log/csp-report`, {
      headers: { 'Content-Type': 'application/csp-report' },
      data: JSON.stringify({
        'csp-report': {
          'document-uri': 'http://127.0.0.1:3200/products?credential=e2e-sensitive#fragment',
          'blocked-uri': 'inline',
          'effective-directive': 'script-src-elem',
          'violated-directive': "script-src 'self'",
          disposition: 'report',
        },
      }),
    })

    expect(legacyResponse.status()).toBe(202)
    expect(await legacyResponse.json()).toEqual({
      accepted: 1,
      sampled: 0,
      persist_failed: 0,
    })

    const reportingResponse = await request.post(`${API_BASE}/api/log/csp-report`, {
      headers: { 'Content-Type': 'application/reports+json' },
      data: JSON.stringify([
        {
          type: 'csp-violation',
          age: 0,
          url: 'http://127.0.0.1:3200/',
          body: {
            documentURL: 'http://127.0.0.1:3200/?credential=e2e-sensitive#fragment',
            blockedURL: 'eval',
            effectiveDirective: 'script-src',
            disposition: 'report',
          },
        },
      ]),
    })

    expect(reportingResponse.status()).toBe(202)
    expect(await reportingResponse.json()).toEqual({
      accepted: 1,
      sampled: 0,
      persist_failed: 0,
    })
  })

  test('认证恢复、SSE cookie、Bearer 写入与退出边界保持有效', async ({ page }) => {
    await login(page)

    expect(await getAuthCookieState(page)).toEqual({
      hasHttpOnlyAccessCookie: true,
      hasHttpOnlyRefreshCookie: true,
    })

    await page.context().clearCookies({ name: ACCESS_COOKIE_NAME })
    await page.evaluate(() => {
      localStorage.setItem('futures_access_token', 'invalid-memory-token')
    })
    expect(await getAuthCookieState(page)).toEqual({
      hasHttpOnlyAccessCookie: false,
      hasHttpOnlyRefreshCookie: true,
    })

    const rejectedMe = page.waitForResponse(
      (response) => response.url().endsWith('/api/auth/me') && response.status() === 401,
    )
    const refreshed = page.waitForResponse(
      (response) => response.url().endsWith('/api/auth/refresh') && response.status() === 200,
    )
    await page.reload()
    await rejectedMe
    await refreshed
    await expect(page.getByRole('heading', { name: '行情工作台' })).toBeVisible({ timeout: 15000 })

    const restoredTokenState = await page.evaluate(() => {
      const token = localStorage.getItem('futures_access_token')
      return {
        isJwt: token?.startsWith('eyJ') === true,
        replacedInvalidToken: token !== 'invalid-memory-token',
      }
    })
    expect(restoredTokenState).toEqual({
      isJwt: true,
      replacedInvalidToken: true,
    })
    expect(await getAuthCookieState(page)).toEqual({
      hasHttpOnlyAccessCookie: true,
      hasHttpOnlyRefreshCookie: true,
    })

    let forced401Count = 0
    let refreshRequestCount = 0
    let recoveredResponseCount = 0
    let releaseConcurrent401!: () => void
    const concurrent401Barrier = new Promise<void>((resolve) => {
      releaseConcurrent401 = resolve
    })
    const recoveryPaths = new Set(['/api/workspace/me', '/api/varieties'])
    const concurrent401Route = async (route: Route) => {
      const request = route.request()
      const url = new URL(request.url())
      if (url.origin !== API_ORIGIN) {
        await route.continue()
        return
      }
      if (url.pathname === '/api/auth/refresh') {
        refreshRequestCount += 1
        await route.continue()
        return
      }
      if (
        request.method() === 'GET' &&
        recoveryPaths.has(url.pathname) &&
        forced401Count < 2
      ) {
        forced401Count += 1
        if (forced401Count === 2) {
          releaseConcurrent401()
        }
        await concurrent401Barrier
        await route.fulfill({
          status: 401,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'expired access token' }),
        })
        return
      }
      await route.continue()
    }
    page.on('response', (response) => {
      const url = new URL(response.url())
      if (
        url.origin === API_ORIGIN &&
        recoveryPaths.has(url.pathname) &&
        response.status() === 200
      ) {
        recoveredResponseCount += 1
      }
    })
    await page.route(`${API_BASE}/api/**`, concurrent401Route)
    await page.goto('/workspace')

    await expect.poll(
      () => forced401Count,
      { message: 'workspace should receive two concurrent 401 responses', timeout: 15000 },
    ).toBe(2)
    await expect.poll(
      () => refreshRequestCount,
      { message: 'concurrent 401 responses should share one refresh request', timeout: 15000 },
    ).toBe(1)
    await expect.poll(
      () => recoveredResponseCount,
      { message: 'workspace requests should succeed after the shared refresh', timeout: 15000 },
    ).toBeGreaterThanOrEqual(2)
    await expect(page.getByRole('heading', { name: '我的工作区' })).toBeVisible()
    expect(refreshRequestCount).toBe(1)
    expect(await getAuthCookieState(page)).toEqual({
      hasHttpOnlyAccessCookie: true,
      hasHttpOnlyRefreshCookie: true,
    })
    await page.unroute(`${API_BASE}/api/**`, concurrent401Route)

    const sseAttempts: Array<{ hasHttpOnlyAccessCookie: boolean }> = []
    const sseRoute = async (route: Route) => {
      const request = route.request()
      const attempt = sseAttempts.length + 1
      sseAttempts.push({
        hasHttpOnlyAccessCookie: await requestHasCookie(request, ACCESS_COOKIE_NAME),
      })
      if (attempt === 1) {
        await route.abort('connectionfailed')
        return
      }
      if (attempt === 2) {
        await route.continue()
        return
      }
      await route.abort('connectionfailed')
    }
    await page.route(`${API_BASE}/api/realtime/stream**`, sseRoute)
    const successfulStreamResponse = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/api/realtime/stream' &&
        response.status() === 200,
      { timeout: 15000 },
    )
    const sseResultPromise = page.evaluate((apiBase) => new Promise<{
      data: string
      errorCount: number
    }>((resolve, reject) => {
      const stream = new EventSource(`${apiBase}/api/realtime/stream?symbols=AU`, {
        withCredentials: true,
      })
      let errorCount = 0
      const timeoutId = window.setTimeout(() => {
        stream.close()
        reject(new Error(`SSE reconnect timed out after ${errorCount} connection errors`))
      }, 15000)
      stream.onmessage = (event) => {
        window.clearTimeout(timeoutId)
        stream.close()
        resolve({ data: event.data, errorCount })
      }
      stream.onerror = () => {
        errorCount += 1
      }
    }), API_BASE)

    await expect.poll(
      () => sseAttempts.length,
      { message: 'EventSource should reconnect after the first network failure', timeout: 15000 },
    ).toBeGreaterThanOrEqual(2)
    const [streamResponse, sseResult] = await Promise.all([
      successfulStreamResponse,
      sseResultPromise,
    ])
    expect(streamResponse.status()).toBe(200)
    expect(sseAttempts).toHaveLength(2)
    expect(sseAttempts[1].hasHttpOnlyAccessCookie).toBe(true)
    expect(streamResponse.url()).not.toContain('token=')
    expect(sseResult.errorCount).toBeGreaterThanOrEqual(1)
    expect(sseResult.data).toContain('"quotes"')
    await page.unroute(`${API_BASE}/api/realtime/stream**`, sseRoute)

    const writeRequestPromise = page.waitForRequest(async (request) => {
      if (
        !request.url().endsWith('/api/price-levels') ||
        request.method() !== 'POST'
      ) {
        return false
      }
      return (await request.allHeaders()).authorization?.startsWith('Bearer ') === true
    })
    const writeResult = await page.evaluate(async (apiBase) => {
      const token = localStorage.getItem('futures_access_token')
      const varietiesResponse = await fetch(`${apiBase}/api/varieties?limit=1`, {
        credentials: 'include',
        headers: { Authorization: `Bearer ${token}` },
      })
      const varieties = await varietiesResponse.json()
      const varietyId = varieties[0]?.id
      if (!varietyId) throw new Error('No variety available for the write contract')

      const payload = {
        variety_id: varietyId,
        type: 'support',
        price: (1000 + (Date.now() % 1_000_000) / 100).toFixed(2),
        scope: 'continuous',
        note: 'R9 CSP E2E',
      }
      const cookieOnly = await fetch(`${apiBase}/api/price-levels`, {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const created = await fetch(`${apiBase}/api/price-levels`, {
        method: 'POST',
        credentials: 'include',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      })
      const createdBody = await created.json()
      const removed = await fetch(`${apiBase}/api/price-levels/${createdBody.id}`, {
        method: 'DELETE',
        credentials: 'include',
        headers: { Authorization: `Bearer ${token}` },
      })
      return {
        cookieOnlyStatus: cookieOnly.status,
        createdStatus: created.status,
        removedStatus: removed.status,
      }
    }, API_BASE)
    const writeRequest = await writeRequestPromise
    expect(await requestHasBearerAuthorization(writeRequest)).toBe(true)
    expect(writeResult).toEqual({
      cookieOnlyStatus: 401,
      createdStatus: 201,
      removedStatus: 200,
    })

    const logoutResponse = page.waitForResponse(
      (response) => response.url().endsWith('/api/auth/logout') && response.status() === 200,
    )
    await page.getByRole('button', { name: '退出' }).click()
    await logoutResponse
    await expect(page.getByText('倍增计划是私密交流社区')).toBeVisible()
    expect(await page.evaluate(
      (accessTokenKey) => localStorage.getItem(accessTokenKey) === null,
      ACCESS_TOKEN_KEY,
    )).toBe(true)
    expect(await getAuthCookieState(page)).toEqual({
      hasHttpOnlyAccessCookie: false,
      hasHttpOnlyRefreshCookie: false,
    })
  })
})
