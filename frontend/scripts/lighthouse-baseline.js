/**
 * Lighthouse performance trend collector.
 *
 * Usage:
 *   node scripts/lighthouse-baseline.js [http://127.0.0.1:3200]
 *
 * Optional environment:
 *   LIGHTHOUSE_ROUTES="home=/,products=/products"
 *   LIGHTHOUSE_HISTORY_LIMIT=240
 *
 * The script measures public route renders only. Authenticated product-detail
 * behavior remains covered by Playwright smoke tests.
 */

const fs = require('fs')
const path = require('path')
const lighthouse = require('lighthouse').default
const chromeLauncher = require('chrome-launcher')

const OUTPUT_DIR = path.join(__dirname, '../.lighthouse')
const HISTORY_LIMIT = Number.parseInt(process.env.LIGHTHOUSE_HISTORY_LIMIT ?? '240', 10)
const DEFAULT_ROUTES = Object.freeze([
  { name: 'home', path: '/' },
  { name: 'products', path: '/products' },
])

const THRESHOLDS = Object.freeze({
  lcp: 5000,
  fcp: 3000,
  tbt: 600,
  cls: 0.25,
  si: 5000,
})

function normalizeBaseUrl(value) {
  const parsed = new URL(value)
  if (!['http:', 'https:'].includes(parsed.protocol)) {
    throw new Error(`Unsupported Lighthouse base URL: ${value}`)
  }
  return parsed.toString().replace(/\/$/, '')
}

function parseRouteConfig(value) {
  if (!value) return [...DEFAULT_ROUTES]

  const routes = value.split(',').map((item) => {
    const [name, routePath, ...rest] = item.trim().split('=')
    if (!name || !routePath || rest.length > 0 || !routePath.startsWith('/')) {
      throw new Error(`Invalid LIGHTHOUSE_ROUTES entry: ${item}`)
    }
    if (!/^[a-z0-9][a-z0-9_-]*$/i.test(name)) {
      throw new Error(`Invalid Lighthouse route name: ${name}`)
    }
    return { name, path: routePath }
  })

  const names = new Set(routes.map((route) => route.name))
  if (names.size !== routes.length) {
    throw new Error('Lighthouse route names must be unique')
  }
  return routes
}

function resolveRoutes(baseUrl, routeConfig = process.env.LIGHTHOUSE_ROUTES) {
  return parseRouteConfig(routeConfig).map((route) => ({
    ...route,
    url: new URL(route.path, `${normalizeBaseUrl(baseUrl)}/`).toString(),
  }))
}

function createRunMetadata(environment = process.env, now = new Date()) {
  return {
    collectedAt: now.toISOString(),
    commitSha: environment.GITHUB_SHA ?? environment.CI_COMMIT_SHA ?? null,
    ref: environment.GITHUB_REF_NAME ?? environment.CI_COMMIT_REF_NAME ?? null,
    repository: environment.GITHUB_REPOSITORY ?? environment.CI_PROJECT_PATH ?? null,
    runId: environment.GITHUB_RUN_ID ?? environment.CI_PIPELINE_ID ?? null,
    runAttempt: environment.GITHUB_RUN_ATTEMPT ?? null,
    workflow: environment.GITHUB_WORKFLOW ?? null,
    eventName: environment.GITHUB_EVENT_NAME ?? null,
    environment: environment.CI || environment.GITHUB_ACTIONS ? 'ci' : 'local',
  }
}

function getMetrics(lhr) {
  const audits = lhr.audits
  const getAudit = (key) => audits[key] ?? {}
  const getNumeric = (key) => getAudit(key).numericValue ?? null

  return {
    performanceScore: Math.round((lhr.categories.performance.score ?? 0) * 100),
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
}

function findThresholdFailures(metrics) {
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
  return failures
}

function createRouteRecord(route, lhr, run) {
  const metrics = getMetrics(lhr)
  return {
    timestamp: lhr.fetchTime ?? run.collectedAt,
    route,
    run,
    metrics,
    thresholdFailures: findThresholdFailures(metrics),
  }
}

function readHistory(historyPath) {
  if (!fs.existsSync(historyPath)) return []
  try {
    const parsed = JSON.parse(fs.readFileSync(historyPath, 'utf8'))
    if (!Array.isArray(parsed.entries)) {
      throw new Error('missing entries array')
    }
    return parsed.entries.filter((entry) => (
      entry
      && typeof entry.timestamp === 'string'
      && typeof entry.route?.name === 'string'
      && typeof entry.metrics === 'object'
    ))
  } catch (error) {
    console.warn(`Ignoring invalid Lighthouse history at ${historyPath}: ${error.message}`)
    return []
  }
}

function historyKey(record) {
  const source = record.run?.commitSha ?? record.run?.runId ?? record.timestamp
  return `${source}:${record.route.name}`
}

function mergeHistory(existingEntries, currentEntries, limit = HISTORY_LIMIT) {
  const entriesByKey = new Map()
  for (const entry of [...existingEntries, ...currentEntries]) {
    entriesByKey.set(historyKey(entry), entry)
  }
  return [...entriesByKey.values()]
    .sort((left, right) => left.timestamp.localeCompare(right.timestamp))
    .slice(-Math.max(1, limit))
}

function findPreviousRecord(record, history) {
  return history
    .filter((candidate) => (
      candidate.route.name === record.route.name
      && candidate.run?.commitSha !== record.run?.commitSha
      && (!record.run?.ref || candidate.run?.ref === record.run.ref)
    ))
    .sort((left, right) => left.timestamp.localeCompare(right.timestamp))
    .at(-1) ?? null
}

function buildComparison(record, history) {
  const previous = findPreviousRecord(record, history)
  if (!previous) return null

  const metricKeys = [
    'performanceScore',
    'firstContentfulPaint',
    'largestContentfulPaint',
    'totalBlockingTime',
    'cumulativeLayoutShift',
    'speedIndex',
    'timeToInteractive',
    'totalByteWeight',
  ]
  const deltas = Object.fromEntries(metricKeys.map((key) => [
    key,
    record.metrics[key] - previous.metrics[key],
  ]))
  return {
    previousCommitSha: previous.run?.commitSha ?? null,
    previousTimestamp: previous.timestamp,
    deltas,
  }
}

function buildTrendReport({ run, routeRecords, history }) {
  const routes = routeRecords.map((record) => ({
    ...record,
    comparison: buildComparison(record, history),
  }))
  const entries = mergeHistory(history, routes)
  return {
    schemaVersion: 1,
    generatedAt: run.collectedAt,
    run,
    routes,
    history: {
      retainedEntries: entries.length,
      entries,
    },
  }
}

function writeReports(outputDir, report) {
  fs.mkdirSync(outputDir, { recursive: true })
  const historyDocument = {
    schemaVersion: report.schemaVersion,
    generatedAt: report.generatedAt,
    entries: report.history.entries,
  }
  const writeJson = (name, value) => {
    fs.writeFileSync(path.join(outputDir, name), `${JSON.stringify(value, null, 2)}\n`)
  }

  writeJson('lighthouse-trend.json', report)
  writeJson('lighthouse-history.json', historyDocument)
  writeJson('latest.json', report)
}

function printRecord(record) {
  const { metrics } = record
  console.log(`\n=== Lighthouse: ${record.route.name} (${record.route.path}) ===`)
  console.log(`URL: ${record.route.url}`)
  console.log(`Performance Score: ${metrics.performanceScore}/100`)
  console.log(`FCP: ${metrics.firstContentfulPaint}ms`)
  console.log(`LCP: ${metrics.largestContentfulPaint}ms`)
  console.log(`TBT: ${metrics.totalBlockingTime}ms`)
  console.log(`CLS: ${metrics.cumulativeLayoutShift}`)
  console.log(`SI: ${metrics.speedIndex}ms`)
  console.log(`TTI: ${metrics.timeToInteractive}ms`)
  console.log(`DOM size: ${metrics.domSize}`)
  console.log(`Network requests: ${metrics.networkRequests}`)
  console.log(`Total weight: ${metrics.totalByteWeight}KB`)
}

async function run() {
  const baseUrl = normalizeBaseUrl(process.argv[2] || 'http://127.0.0.1:3200')
  const routes = resolveRoutes(baseUrl)
  const runMetadata = createRunMetadata()
  const historyPath = path.join(OUTPUT_DIR, 'lighthouse-history.json')
  const existingHistory = readHistory(historyPath)
  const chrome = await chromeLauncher.launch({ chromeFlags: ['--headless', '--disable-gpu'] })

  try {
    const routeRecords = []
    for (const route of routes) {
      const runnerResult = await lighthouse(route.url, {
        port: chrome.port,
        output: 'json',
        onlyCategories: ['performance'],
      })
      if (!runnerResult) {
        throw new Error(`Lighthouse failed for route ${route.name}: no result`)
      }
      const record = createRouteRecord(route, runnerResult.lhr, runMetadata)
      routeRecords.push(record)
      printRecord(record)
    }

    const report = buildTrendReport({
      run: runMetadata,
      routeRecords,
      history: existingHistory,
    })
    writeReports(OUTPUT_DIR, report)

    const failures = report.routes.flatMap((record) => (
      record.thresholdFailures.map((failure) => `${record.route.name}: ${failure}`)
    ))
    if (failures.length > 0) {
      console.log('\nLighthouse threshold failures:')
      failures.forEach((failure) => console.log(`  - ${failure}`))
      process.exitCode = 1
    } else {
      console.log('\nAll Lighthouse metrics passed their thresholds.')
    }
    console.log(`Trend report saved: ${path.join(OUTPUT_DIR, 'lighthouse-trend.json')}`)
  } finally {
    await chrome.kill()
  }
}

module.exports = {
  DEFAULT_ROUTES,
  THRESHOLDS,
  buildTrendReport,
  createRunMetadata,
  mergeHistory,
  parseRouteConfig,
  resolveRoutes,
}

if (require.main === module) {
  run().catch((error) => {
    console.error(error)
    process.exitCode = 1
  })
}
