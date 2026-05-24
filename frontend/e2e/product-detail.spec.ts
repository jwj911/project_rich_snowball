import { test, expect, Page } from '@playwright/test'

async function login(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: '登录' }).click()
  await page.getByLabel('用户名').fill('trader001')
  await page.getByLabel('密码').fill('password123')
  await page.getByRole('button', { name: '登录' }).click()
  await expect(page.getByRole('heading', { name: '行情工作台' })).toBeVisible({ timeout: 10000 })
}

async function enterFirstProductDetail(page: Page) {
  await page.goto('/products')
  await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 10000 })
  await page.getByRole('link', { name: '详情' }).first().click()
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
}

test.describe.serial('品种详情页', () => {
  test('详情页应显示品种信息与 K 线图', async ({ page }) => {
    await login(page)
    await enterFirstProductDetail(page)

    await expect(page.getByRole('button', { name: '连续 K 线' })).toBeVisible()
    await expect(page.getByRole('button', { name: '主力合约' })).toBeVisible()
    await expect(page.getByRole('button', { name: '具体合约' })).toBeVisible()
    await expect(page.getByRole('img')).toBeVisible({ timeout: 15000 })
  })

  test('K 线源切换应更新图表状态', async ({ page }) => {
    await login(page)
    await enterFirstProductDetail(page)

    await page.getByRole('button', { name: '主力合约' }).click()
    await expect(page.getByRole('button', { name: '主力合约' })).toHaveClass(/border-amber-500/)

    await page.getByRole('button', { name: '具体合约' }).click()
    const contractSelect = page.getByLabel('选择具体合约')
    if (await contractSelect.isVisible().catch(() => false)) {
      const options = await contractSelect.locator('option').count()
      if (options > 1) {
        await contractSelect.selectOption({ index: 1 })
      }
    }

    await page.getByRole('button', { name: '连续 K 线' }).click()
    await expect(page.getByRole('button', { name: '连续 K 线' })).toHaveClass(/border-amber-500/)
  })

  test('加入自选与取消自选应可正常工作', async ({ page }) => {
    await login(page)
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
    await login(page)
    await enterFirstProductDetail(page)

    const supportSection = page.locator('section').filter({ hasText: '支撑位' }).first()
    const input = supportSection.getByLabel('支撑位')
    await input.fill('1234.56')
    await supportSection.getByRole('button', { name: '添加' }).click()

    await expect(supportSection.getByText('1234.56')).toBeVisible()

    await supportSection.getByRole('button', { name: '删除支撑位 1234.56' }).click()
    await expect(supportSection.getByText('1234.56')).not.toBeVisible()
  })

  test('添加与删除阻力位应可正常工作', async ({ page }) => {
    await login(page)
    await enterFirstProductDetail(page)

    const resistanceSection = page.locator('section').filter({ hasText: '阻力位' }).first()
    const input = resistanceSection.getByLabel('阻力位')
    await input.fill('5678.90')
    await resistanceSection.getByRole('button', { name: '添加' }).click()

    await expect(resistanceSection.getByText('5678.90')).toBeVisible()

    await resistanceSection.getByRole('button', { name: '删除阻力位 5678.90' }).click()
    await expect(resistanceSection.getByText('5678.90')).not.toBeVisible()
  })

  test('发表评论应可正常工作', async ({ page }) => {
    await login(page)
    await enterFirstProductDetail(page)

    const commentInput = page.getByLabel('发表评论')
    const testComment = `E2E 测试评论 ${Date.now()}`
    await commentInput.fill(testComment)
    await page.getByRole('button', { name: '发送' }).click()

    await expect(page.getByText(testComment)).toBeVisible({ timeout: 10000 })
  })

  test('返回行情中心应正常跳转', async ({ page }) => {
    await login(page)
    await enterFirstProductDetail(page)

    await page.getByRole('link', { name: '返回行情中心' }).click()
    await expect(page.getByRole('heading', { name: '行情中心' })).toBeVisible()
  })
})
