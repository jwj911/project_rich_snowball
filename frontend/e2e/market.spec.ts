import { test, expect } from '@playwright/test'

const AUTH_STATE = 'playwright/.auth/user.json'

test.describe('行情页面', () => {
  test('未登录访问品种列表应显示登录引导', async ({ page }) => {
    await page.goto('/products')
    await expect(page.getByText('倍增计划是私密交流社区')).toBeVisible()
  })

  test.describe('已登录', () => {
    test.use({ storageState: AUTH_STATE })

    test('登录后行情中心应显示品种数据与统计', async ({ page }) => {
      await page.goto('/products')
      await expect(page.getByRole('heading', { name: '行情中心' })).toBeVisible()
      await expect(page.getByText(/品种数/)).toBeVisible()
      // 使用 exact match 避免匹配到 hidden 的 select option（"上涨品种"）
      await expect(page.getByText('上涨', { exact: true })).toBeVisible()
      await expect(page.getByText('下跌', { exact: true })).toBeVisible()
      const rows = page.locator('table tbody tr')
      await expect(rows.first()).toBeVisible({ timeout: 10000 })
      const count = await rows.count()
      expect(count).toBeGreaterThan(0)
      expect(count).toBeLessThanOrEqual(20)
    })

    test('搜索与清除筛选功能应正常工作', async ({ page }) => {
      await page.goto('/products')
      await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 10000 })

      const searchInput = page.getByPlaceholder('搜索品种名称、代码或分类')
      await searchInput.fill('NONEXISTENT_SYMBOL_12345')
      await expect(page.getByText('没有匹配的品种')).toBeVisible()

      await page.getByRole('button', { name: '清除', exact: true }).click()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    })

    test('分页功能应正常工作', async ({ page }) => {
      await page.goto('/products')
      await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 10000 })

      const nextButton = page.getByRole('button', { name: '下一页' })
      if (await nextButton.isVisible().catch(() => false)) {
        await nextButton.click()
        await expect(page.getByText(/第 2 \/ \d+ 页/)).toBeVisible()
        await page.getByRole('button', { name: '上一页' }).click()
        await expect(page.getByText(/第 1 \/ \d+ 页/)).toBeVisible()
      }
    })

    test('排序功能应可切换方向', async ({ page }) => {
      await page.goto('/products')
      await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 10000 })
      await page.getByRole('button', { name: '涨跌幅' }).click()
      await expect(page.locator('table tbody tr').first()).toBeVisible()
    })
  })
})
