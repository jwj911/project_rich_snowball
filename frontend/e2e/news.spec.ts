import { test, expect } from '@playwright/test'

const AUTH_STATE = 'playwright/.auth/user.json'

test.describe('新闻资讯页面', () => {
  test('未登录访问 /news 应显示登录门禁', async ({ page }) => {
    await page.goto('/news')
    const main = page.getByRole('main')
    await expect(main.getByText('倍增计划是私密交流社区')).toBeVisible()
    await expect(main.getByRole('button', { name: '登录' })).toBeVisible()
  })

  test('未登录访问 /news 不应加载新闻列表', async ({ page }) => {
    await page.goto('/news')
    const main = page.getByRole('main')
    // 不应显示新闻相关的特有内容
    await expect(main.getByText('新闻资讯')).not.toBeVisible()
    await expect(main.getByText('聚合市场新闻与行业动态')).not.toBeVisible()
  })

  test.describe('已登录', () => {
    test.use({ storageState: AUTH_STATE })

    test('已登录访问 /news 应正常加载新闻列表', async ({ page }) => {
      await page.goto('/news')

      // 应显示新闻页面标题和描述
      await expect(page.getByRole('heading', { name: '新闻资讯' })).toBeVisible({ timeout: 10000 })
      await expect(page.getByText('聚合市场新闻与行业动态')).toBeVisible()

      // 应显示数据源数量或新闻内容
      await expect(page.getByText(/个数据源/)).toBeVisible()
    })

    test('新闻页面搜索框应可输入', async ({ page }) => {
      await page.goto('/news')
      await expect(page.getByRole('heading', { name: '新闻资讯' })).toBeVisible({ timeout: 10000 })

      const searchInput = page.getByPlaceholder('搜索新闻标题...')
      await expect(searchInput).toBeVisible()

      // 输入搜索词后不应立即触发请求（防抖）
      await searchInput.fill('测试')
      // 等待短暂时间，确认页面未崩溃
      await expect(page.getByRole('heading', { name: '新闻资讯' })).toBeVisible()
    })
  })
})
