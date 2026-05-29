import { test as setup, expect } from '@playwright/test'

const authFile = 'playwright/.auth/user.json'

setup('authenticate', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('navigation').getByRole('button', { name: '登录' }).click()
  await page.getByLabel('用户名').fill('trader001')
  await page.getByLabel('密码').fill('password123')
  await page.getByRole('dialog', { name: '登录' }).getByRole('button', { name: '登录' }).click()
  await expect(page.getByRole('heading', { name: '行情工作台' })).toBeVisible({ timeout: 15000 })

  await page.context().storageState({ path: authFile })
})
