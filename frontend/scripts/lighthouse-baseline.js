/**
 * Lighthouse 性能基线脚本
 *
 * 用法：
 *   node scripts/lighthouse-baseline.js [http://127.0.0.1:3200]
 *
 * 说明：
 * - 使用 headless Chrome（无需后端登录态）测量首页未登录态性能
 * - 输出 LCP、TBT、CLS、FCP、SI 等核心 Web Vitals
 * - 阈值基于开发模式（首次编译较慢），CI 环境应使用 production build
 */

const fs = require('fs')
const path = require('path')
const lighthouse = require('lighthouse').default
const chromeLauncher = require('chrome-launcher')

const TARGET_URL = process.argv[2] || 'http://127.0.0.1:3200'
const OUTPUT_DIR = path.join(__dirname, '../.lighthouse')

const THRESHOLDS = {
  // 开发模式阈值（较宽松）
  lcp: 5000,
  fcp: 3000,
  tbt: 600,
  cls: 0.25,
  si: 5000,
}

async function run() {
  const chrome = await chromeLauncher.launch({ chromeFlags: ['--headless', '--disable-gpu'] })

  try {
    const runnerResult = await lighthouse(TARGET_URL, {
      port: chrome.port,
      output: 'json',
      onlyCategories: ['performance'],
    })

    if (!runnerResult) {
      console.error('Lighthouse failed: no result')
      process.exit(1)
    }

    const { lhr } = runnerResult
    const perf = lhr.categories.performance.score * 100
    const audits = lhr.audits

    const getAudit = (key) => audits[key] ?? {}
    const getNumeric = (key) => getAudit(key).numericValue ?? null

    const metrics = {
      url: TARGET_URL,
      timestamp: new Date().toISOString(),
      performanceScore: perf,
      firstContentfulPaint: Math.round(getNumeric('first-contentful-paint') ?? 0),
      largestContentfulPaint: Math.round(getNumeric('largest-contentful-paint') ?? 0),
      totalBlockingTime: Math.round(getNumeric('total-blocking-time') ?? 0),
      cumulativeLayoutShift: Math.round((getNumeric('cumulative-layout-shift') ?? 0) * 1000) / 1000,
      speedIndex: Math.round(getNumeric('speed-index') ?? 0),
      timeToInteractive: Math.round(getNumeric('interactive') ?? 0),
      domSize: getNumeric('dom-size') ?? null,
      networkRequests: getAudit('network-requests').details?.items?.length ?? null,
      totalByteWeight: Math.round((getNumeric('total-byte-weight') ?? 0) / 1024),
    }

    // 输出到控制台
    console.log('\n=== Lighthouse 性能基线 ===')
    console.log(`URL: ${metrics.url}`)
    console.log(`Performance Score: ${metrics.performanceScore}/100`)
    console.log(`FCP: ${metrics.firstContentfulPaint}ms`)
    console.log(`LCP: ${metrics.largestContentfulPaint}ms`)
    console.log(`TBT: ${metrics.totalBlockingTime}ms`)
    console.log(`CLS: ${metrics.cumulativeLayoutShift}`)
    console.log(`SI:  ${metrics.speedIndex}ms`)
    console.log(`TTI: ${metrics.timeToInteractive}ms`)
    console.log(`DOM size: ${metrics.domSize}`)
    console.log(`Network requests: ${metrics.networkRequests}`)
    console.log(`Total weight: ${metrics.totalByteWeight}KB`)

    // 阈值检查
    const failures = []
    if (metrics.largestContentfulPaint > THRESHOLDS.lcp) {
      failures.push(`LCP ${metrics.largestContentfulPaint}ms > ${THRESHOLDS.lcp}ms`)
    }
    if (metrics.firstContentfulPaint > THRESHOLDS.fcp) {
      failures.push(`FCP ${metrics.firstContentfulPaint}ms > ${THRESHOLDS.fcp}ms`)
    }
    if (metrics.totalBlockingTime > THRESHOLDS.tbt) {
      failures.push(`TBT ${metrics.totalBlockingTime}ms > ${THRESHOLDS.tbt}ms`)
    }
    if (metrics.cumulativeLayoutShift > THRESHOLDS.cls) {
      failures.push(`CLS ${metrics.cumulativeLayoutShift} > ${THRESHOLDS.cls}`)
    }
    if (metrics.speedIndex > THRESHOLDS.si) {
      failures.push(`SI ${metrics.speedIndex}ms > ${THRESHOLDS.si}ms`)
    }

    if (failures.length > 0) {
      console.log('\n⚠️ 阈值未通过（开发模式可放宽）：')
      failures.forEach((f) => console.log(`  - ${f}`))
    } else {
      console.log('\n✅ 所有指标通过阈值')
    }

    // 写入报告文件
    if (!fs.existsSync(OUTPUT_DIR)) fs.mkdirSync(OUTPUT_DIR, { recursive: true })
    const reportPath = path.join(OUTPUT_DIR, `baseline-${Date.now()}.json`)
    fs.writeFileSync(reportPath, JSON.stringify(metrics, null, 2))
    console.log(`\n报告已保存: ${reportPath}`)

    // 同时保存最新报告用于对比
    const latestPath = path.join(OUTPUT_DIR, 'latest.json')
    fs.writeFileSync(latestPath, JSON.stringify(metrics, null, 2))

    process.exit(failures.length > 0 ? 1 : 0)
  } finally {
    await chrome.kill()
  }
}

run().catch((err) => {
  console.error(err)
  process.exit(1)
})
