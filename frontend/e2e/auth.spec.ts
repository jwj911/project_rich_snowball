import { test, expect, Page } from '@playwright/test'

async function openLoginModal(page: Page) {
  await page.goto('/')
  await page.getByRole('button', { name: '登录' }).click()
}

async function submitLogin(page: Page, username = 'trader001', password = 'password123') {
  await page.getByLabel('用户名').fill(username)
  await page.getByLabel('密码').fill(password)
  await page.getByRole('button', { name: '登录' }).click()
}

test.describe('登录与权限', () => {
  test('未登录访问首页应显示登录引导', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByText('倍增计划是私密交流社区')).toBeVisible()
    await expect(page.getByRole('button', { name: '登录' })).toBeVisible()
  })

  test('登录弹窗应具备标准 dialog 语义与焦点管理', async ({ page }) => {
    await openLoginModal(page)
    const dialog = page.getByRole('dialog', { name: '登录' })
    await expect(dialog).toBeVisible()
    await expect(dialog).toHaveAttribute('aria-modal', 'true')
    await expect(page.getByLabel('用户名')).toBeFocused()
    await page.keyboard.press('Escape')
    await expect(dialog).not.toBeVisible()
  })

  test('登录成功后应显示行情工作台', async ({ page }) => {
    await openLoginModal(page)
    await submitLogin(page)
    await expect(page.getByRole('heading', { name: '行情工作台' })).toBeVisible({ timeout: 10000 })
  })

  test('登录后 localStorage 不应持久化 access token', async ({ page }) => {
    await openLoginModal(page)
    await submitLogin(page)
    await expect(page.getByRole('heading', { name: '行情工作台' })).toBeVisible({ timeout: 10000 })
    const token = await page.evaluate(() => localStorage.getItem('token'))
    expect(token).toBeNull()
  })

  test('退出登录后应回到未登录状态', async ({ page }) => {
    await openLoginModal(page)
    await submitLogin(page)
    await expect(page.getByRole('heading', { name: '行情工作台' })).toBeVisible({ timeout: 10000 })

    await page.getByRole('button', { name: '退出' }).click()
    await expect(page.getByText('倍增计划是私密交流社区')).toBeVisible()
    await expect(page.getByRole('button', { name: '登录' })).toBeVisible()
  })

  test('可从登录弹窗切换到注册弹窗并返回', async ({ page }) => {
    await openLoginModal(page)
    await expect(page.getByRole('dialog', { name: '登录' })).toBeVisible()
    await page.getByRole('button', { name: '注册' }).click()
    await expect(page.getByRole('dialog', { name: '注册' })).toBeVisible()
    await expect(page.getByLabel('邮箱')).toBeVisible()
    await page.getByRole('button', { name: '去登录' }).click()
    await expect(page.getByRole('dialog', { name: '登录' })).toBeVisible()
  })
})
