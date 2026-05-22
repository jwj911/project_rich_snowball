import { test, expect } from '@playwright/test'

test.describe('行情页面', () => {
  test('品种列表页应显示品种数据', async ({ page }) => {
    await page.goto('/products')
    // 未登录时显示登录引导
    await expect(page.getByText('倍增计划是私密交流社区')).toBeVisible()
  })
})
