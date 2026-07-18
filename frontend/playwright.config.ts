import { defineConfig, devices } from '@playwright/test'

const useExternalWebServer = process.env.E2E_EXTERNAL_SERVER === '1'

/**
 * Playwright E2E 配置
 *
 * 注意：auth.setup.ts 及所有已登录测试需要后端 API 在 http://127.0.0.1:8401 运行。
 * 若只测未登录流程，可直接运行 npx playwright test。
 * 性能基线优先使用 Lighthouse（npm run lighthouse），不依赖后端登录态。
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:3200',
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'setup',
      testMatch: /auth\.setup\.ts/,
    },
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
      dependencies: ['setup'],
    },
  ],

  webServer: useExternalWebServer
    ? undefined
    : {
        command: 'npm run dev',
        url: 'http://127.0.0.1:3200',
        reuseExistingServer: !process.env.CI,
        timeout: 120 * 1000,
      },
})
