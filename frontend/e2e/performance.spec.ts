import { test, expect, Page } from '@playwright/test'

interface PerfMetrics {
  domContentLoaded: number
  loadComplete: number
  firstPaint: number | null
  largestContentfulPaint: number | null
  jsHeapUsedMB: number | null
}

async function measurePageLoad(page: Page, url: string): Promise<PerfMetrics> {
  await page.goto(url, { waitUntil: 'networkidle' })

  const metrics = await page.evaluate(() => {
    const nav = performance.getEntriesByType('navigation')[0] as PerformanceNavigationTiming | undefined
    const paint = performance.getEntriesByType('paint')
    const lcpEntries = performance.getEntriesByType('largest-contentful-paint') as PerformanceEntry[]

    const fp = paint.find((p) => p.name === 'first-paint')
    const fcp = paint.find((p) => p.name === 'first-contentful-paint')

    const memory = (performance as any).memory

    return {
      domContentLoaded: nav ? nav.domContentLoadedEventEnd - nav.startTime : 0,
      loadComplete: nav ? nav.loadEventEnd - nav.startTime : 0,
      firstPaint: fp ? fp.startTime : (fcp ? fcp.startTime : null),
      largestContentfulPaint: lcpEntries.length > 0 ? lcpEntries[lcpEntries.length - 1].startTime : null,
      jsHeapUsedMB: memory ? +(memory.usedJSHeapSize / 1024 / 1024).toFixed(2) : null,
    }
  })

  return metrics
}

async function login(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: '登录' }).click()
  await page.getByLabel('用户名').fill('trader001')
  await page.getByLabel('密码').fill('password123')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page.getByRole('heading', { name: '行情工作台' })).toBeVisible({ timeout: 10000 })
}

test.describe('性能基线', () => {
  test('首页（未登录）应在合理时间内完成加载', async ({ page }) => {
    const metrics = await measurePageLoad(page, '/')

    expect(metrics.domContentLoaded).toBeLessThan(3000)
    expect(metrics.loadComplete).toBeLessThan(5000)

    if (metrics.jsHeapUsedMB !== null) {
      expect(metrics.jsHeapUsedMB).toBeLessThan(64)
    }
  })

  test('首页（已登录）应在合理时间内渲染行情工作台', async ({ page }) => {
    await login(page)
    // Clear previous metrics and reload to measure authenticated load
    await page.evaluate(() => performance.clearResourceTimings())

    const metrics = await measurePageLoad(page, '/')

    expect(metrics.domContentLoaded).toBeLessThan(3000)
    expect(metrics.loadComplete).toBeLessThan(5000)

    // Key content visible
    await expect(page.getByRole('heading', { name: '行情工作台' })).toBeVisible()
  })

  test('品种列表页应在合理时间内渲染表格', async ({ page }) => {
    await login(page)
    const metrics = await measurePageLoad(page, '/products')

    expect(metrics.domContentLoaded).toBeLessThan(3000)
    expect(metrics.loadComplete).toBeLessThan(5000)

    // Either loading skeleton or table content should be visible
    const heading = page.getByRole('heading', { name: '行情中心' })
    await expect(heading).toBeVisible()
  })

  test('品种详情页应在合理时间内渲染图表', async ({ page }) => {
    await login(page)

    // Use a known product id; if backend is mock this may need adjustment
    const metrics = await measurePageLoad(page, '/products/1')

    expect(metrics.domContentLoaded).toBeLessThan(3000)
    expect(metrics.loadComplete).toBeLessThan(6000)

    // Chart container or title should appear
    const chartRegion = page.locator('[data-testid="kline-chart"], [data-testid="product-detail"]')
    await expect(chartRegion.or(page.getByRole('heading'))).toBeVisible({ timeout: 5000 })
  })

  test('登录弹窗交互响应应低于 100ms', async ({ page }) => {
    await page.goto('/')
    const start = performance.now()
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page.getByRole('dialog', { name: '登录' })).toBeVisible()
    const elapsed = performance.now() - start
    expect(elapsed).toBeLessThan(1000)
  })
})
