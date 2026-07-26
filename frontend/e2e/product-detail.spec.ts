import { test, expect } from '@playwright/test'

const AUTH_STATE = 'playwright/.auth/user.json'

async function enterFirstProductDetail(page: import('@playwright/test').Page) {
  await page.goto('/products')
  await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 10000 })
  await page.getByRole('link', { name: '详情' }).first().click()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
}

test.describe.serial('品种详情页', () => {
  test.use({ storageState: AUTH_STATE })

  test('详情页应显示品种信息与 K 线图', async ({ page }) => {
    await enterFirstProductDetail(page)

    await expect(page.getByRole('button', { name: '主力合约' })).toBeVisible()
    await expect(page.getByRole('button', { name: '日线' })).toBeVisible()
    // lightweight-charts 渲染为 canvas，不是 img
    await expect(page.locator('canvas').first()).toBeVisible({ timeout: 15000 })
  })

  test('K 线工具栏应使用当前主力日线契约', async ({ page }) => {
    await enterFirstProductDetail(page)

    await expect(page.getByRole('button', { name: '主力合约' })).toBeEnabled()
    await expect(page.getByRole('button', { name: '日线' })).toBeEnabled()
  })

  test('加入自选与取消自选应可正常工作', async ({ page }) => {
    await enterFirstProductDetail(page)

    const watchlistButton = page.getByRole('button', { name: /^加入自选|已自选$/ })
    await expect(watchlistButton).toBeVisible()

    const initialText = await watchlistButton.textContent()
    await watchlistButton.click()

    if (initialText?.includes('加入自选')) {
      await expect(page.getByRole('button', { name: '已自选' })).toBeVisible({ timeout: 10000 })
    } else {
      await expect(page.getByRole('button', { name: '加入自选' })).toBeVisible({ timeout: 10000 })
    }
  })

  test('添加与删除支撑位应可正常工作', async ({ page }) => {
    await enterFirstProductDetail(page)

    const supportPrice = (3000 + Math.random() * 100).toFixed(2)
    const supportSection = page.getByRole('heading', { name: '支撑位', exact: true }).locator('..')
    const input = supportSection.getByLabel('支撑位')
    await input.fill(supportPrice)
    const createResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/api/price-levels') &&
        response.request().method() === 'POST',
    )
    await supportSection.getByRole('button', { name: '添加' }).click()
    await expect((await createResponse).ok()).toBeTruthy()

    const savedSupportLevel = supportSection.getByRole('button', { name: /删除支撑位/ })
    await expect(savedSupportLevel).toBeVisible({ timeout: 15000 })

    await savedSupportLevel.click()
    await expect(savedSupportLevel).not.toBeVisible()
  })

  test('添加与删除阻力位应可正常工作', async ({ page }) => {
    await enterFirstProductDetail(page)

    const resistancePrice = (6000 + Math.random() * 100).toFixed(2)
    const resistanceSection = page.getByRole('heading', { name: '阻力位', exact: true }).locator('..')
    const input = resistanceSection.getByLabel('阻力位')
    await input.fill(resistancePrice)
    const createResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/api/price-levels') &&
        response.request().method() === 'POST',
    )
    await resistanceSection.getByRole('button', { name: '添加' }).click()
    await expect((await createResponse).ok()).toBeTruthy()

    const savedResistanceLevel = resistanceSection.getByRole('button', { name: /删除阻力位/ })
    await expect(savedResistanceLevel).toBeVisible({ timeout: 15000 })

    await savedResistanceLevel.click()
    await expect(savedResistanceLevel).not.toBeVisible()
  })

  test('发表评论应可正常工作', async ({ page }) => {
    await enterFirstProductDetail(page)

    const commentInput = page.getByLabel('发表评论')
    const testComment = `E2E 测试评论 ${Date.now()}`
    await commentInput.fill(testComment)
    await page.getByRole('button', { name: '发送' }).click()

    await expect(page.getByText(testComment)).toBeVisible({ timeout: 10000 })
  })

  test('详情请求失败时应显示可重试错误态', async ({ page }) => {
    await page.route('**/api/varieties/*/detail', async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '详情服务暂不可用' }),
      })
    })

    await page.goto('/products/R5_UNAVAILABLE')

    await expect(page.getByRole('heading', { name: '数据加载失败' })).toBeVisible({ timeout: 10000 })
    await expect(page.getByRole('main').getByText('详情服务暂不可用', { exact: true })).toBeVisible()
    await expect(page.getByRole('button', { name: '重试' })).toBeVisible()
  })

  test('实时行情失败时应保留详情并提示降级', async ({ page }) => {
    await page.route('**/api/realtime/*', async (route) => {
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '实时行情服务暂不可用' }),
      })
    })

    await enterFirstProductDetail(page)

    await expect(page.getByRole('status')).toHaveText('实时行情暂不可用，正在展示最近收盘数据。')
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })

  test('评论提交失败时应在页面内显示原因', async ({ page }) => {
    await page.route('**/api/comments', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '评论服务暂不可用' }),
      })
    })
    await enterFirstProductDetail(page)

    await page.getByLabel('发表评论').fill('无法发送的评论')
    await page.getByRole('button', { name: '发送' }).click()

    await expect(page.getByText('评论服务暂不可用')).toBeVisible()
  })

  test('标注写入失败时应说明已回退本地', async ({ page }) => {
    await page.route('**/api/price-levels*', async (route) => {
      if (route.request().method() !== 'POST') {
        await route.continue()
        return
      }
      await route.fulfill({
        status: 503,
        contentType: 'application/json',
        body: JSON.stringify({ detail: '标注服务暂不可用' }),
      })
    })
    await enterFirstProductDetail(page)

    const supportSection = page.getByRole('heading', { name: '支撑位', exact: true }).locator('..')
    await supportSection.getByLabel('支撑位').fill('3123.45')
    await supportSection.getByRole('button', { name: '添加' }).click()

    await expect(page.getByText('添加失败：标注服务暂不可用，已临时保存到本地。')).toBeVisible()
  })

  test('返回行情中心应正常跳转', async ({ page }) => {
    await enterFirstProductDetail(page)

    await page.getByRole('link', { name: '返回行情中心' }).click()
    await expect(page.getByRole('heading', { name: '行情中心' })).toBeVisible()
  })
})
