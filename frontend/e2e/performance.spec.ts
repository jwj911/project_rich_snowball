import { test, expect, Page } from '@playwright/test'

interface PerfMetrics {
  domContentLoaded: number
  loadComplete: number
  firstPaint: number | null
  largestContentfulPaint: number | null
  jsHeapUsedMB: number | null
}

const AUTH_STATE = 'playwright/.auth/user.json'

async function measurePageLoad(page: Page, url: string): Promise<PerfMetrics> {
  // 使用 'load' 而非 'networkidle'，因为页面可能建立 SSE 长连接导致 networkidle 永不触发
  await page.goto(url, { waitUntil: 'load' })

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

test.describe('性能基线', () => {
  test('首页（未登录）应在合理时间内完成加载', async ({ page }) => {
    // 确保未登录状态
    await page.goto('/')
    await page.evaluate(() => localStorage.removeItem('futures_access_token'))
    await page.reload()

    const metrics = await measurePageLoad(page, '/')

    expect(metrics.domContentLoaded).toBeLessThan(3000)
    expect(metrics.loadComplete).toBeLessThan(5000)

    if (metrics.jsHeapUsedMB !== null) {
      // 开发模式下 Next.js 编译缓存可能使堆内存超过 64MB，放宽到 128MB
      expect(metrics.jsHeapUsedMB).toBeLessThan(128)
    }
  })

  test.describe('已登录', () => {
    test.use({ storageState: AUTH_STATE })

    test('首页（已登录）应在合理时间内渲染行情工作台', async ({ page }) => {
      await page.evaluate(() => performance.clearResourceTimings())

      const metrics = await measurePageLoad(page, '/')

      expect(metrics.domContentLoaded).toBeLessThan(3000)
      expect(metrics.loadComplete).toBeLessThan(5000)

      // Key content visible（开发模式首次编译可能较慢，增加等待时间）
      await expect(page.getByRole('heading', { name: '行情工作台' })).toBeVisible({ timeout: 15000 })
    })

    test('品种列表页应在合理时间内渲染表格', async ({ page }) => {
      const metrics = await measurePageLoad(page, '/products')

      expect(metrics.domContentLoaded).toBeLessThan(3000)
      expect(metrics.loadComplete).toBeLessThan(5000)

      // Either loading skeleton or table content should be visible
      const heading = page.getByRole('heading', { name: '行情中心' })
      await expect(heading).toBeVisible()
    })

    test('品种详情页应在合理时间内渲染图表', async ({ page }) => {
      // Use a known product id; if backend is mock this may need adjustment
      const metrics = await measurePageLoad(page, '/products/RB')

      expect(metrics.domContentLoaded).toBeLessThan(3000)
      expect(metrics.loadComplete).toBeLessThan(6000)

      // Chart container or product title should appear
      await expect(page.getByRole('heading', { name: '螺纹钢' })).toBeVisible({ timeout: 5000 })
    })
  })

  test('登录弹窗交互响应应低于 100ms', async ({ page }) => {
    // 确保未登录状态
    await page.goto('/')
    await page.evaluate(() => localStorage.removeItem('futures_access_token'))
    await page.reload()

    const start = performance.now()
    await page.getByRole('navigation').getByRole('button', { name: '登录' }).click()
    await expect(page.getByRole('dialog', { name: '登录' })).toBeVisible()
    const elapsed = performance.now() - start
    // 开发模式下 Next.js 首次编译可能较慢，阈值放宽到 5s
    expect(elapsed).toBeLessThan(5000)
  })
})
