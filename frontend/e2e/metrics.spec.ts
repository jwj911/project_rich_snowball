import { test, expect } from '@playwright/test'

const AUTH_STATE = 'playwright/.auth/user.json'

test.describe('运营指标面板', () => {
  test('未登录访问应显示登录门禁', async ({ page }) => {
    await page.goto('/metrics')
    await expect(page.getByText('倍增计划是私密交流社区')).toBeVisible()
  })

  test.describe('已登录', () => {
    test.use({ storageState: AUTH_STATE })

    test('已登录用户直接刷新 /metrics 应正常显示，不跳回首页', async ({ page }) => {
      // 直接访问 /metrics（模拟刷新或书签直达）
      await page.goto('/metrics')

      // 不应跳回首页
      await expect(page).not.toHaveURL('/')

      // 应显示指标页内容
      await expect(page.getByRole('heading', { name: '运营指标' })).toBeVisible({ timeout: 10000 })

      // 应显示关键指标卡片
      await expect(page.getByText(/用户数/)).toBeVisible()
      await expect(page.getByText(/评论数/)).toBeVisible()
    })

    test('指标面板应显示多个指标卡片', async ({ page }) => {
      await page.goto('/metrics')
      await expect(page.getByRole('heading', { name: '运营指标' })).toBeVisible({ timeout: 10000 })

      // 至少应有一个关键指标卡片可见
      await expect(page.getByRole('main').getByText(/用户数/)).toBeVisible()
    })
  })
})
