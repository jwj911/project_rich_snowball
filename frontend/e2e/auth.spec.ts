import { test, expect } from '@playwright/test'

test.describe('登录与权限', () => {
  test('未登录访问首页应显示登录引导', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('倍增计划是私密交流社区')).toBeVisible()
    await expect(page.getByRole('button', { name: '登录' })).toBeVisible()
  })

  test('登录成功后应显示行情工作台', async ({ page }) => {
    await page.goto('/')
    await page.getByRole('button', { name: '登录' }).click()
    await page.getByLabel('用户名').fill('trader001')
    await page.getByLabel('密码').fill('password123')
    await page.getByRole('button', { name: '登录' }).click()
    await expect(page.getByText('行情工作台')).toBeVisible({ timeout: 10000 })
  })
})
