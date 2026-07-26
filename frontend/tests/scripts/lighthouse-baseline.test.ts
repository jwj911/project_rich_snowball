import { describe, expect, it } from 'vitest'
import {
  buildTrendReport,
  createRunMetadata,
  mergeHistory,
  parseRouteConfig,
  resolveRoutes,
} from '../../scripts/lighthouse-baseline.js'

function makeRecord(
  commitSha: string,
  timestamp: string,
  overrides: Record<string, unknown> = {},
) {
  return {
    timestamp,
    route: {
      name: 'home',
      path: '/',
      url: 'http://127.0.0.1:3200/',
    },
    run: {
      commitSha,
      ref: 'master',
      environment: 'ci',
    },
    metrics: {
      performanceScore: 90,
      firstContentfulPaint: 1000,
      largestContentfulPaint: 2000,
      totalBlockingTime: 100,
      cumulativeLayoutShift: 0.02,
      speedIndex: 2200,
      timeToInteractive: 2500,
      totalByteWeight: 200,
    },
    thresholdFailures: [],
    ...overrides,
  }
}

describe('lighthouse trend collector', () => {
  it('uses named routes with stable URLs', () => {
    expect(parseRouteConfig('home=/,products=/products')).toEqual([
      { name: 'home', path: '/' },
      { name: 'products', path: '/products' },
    ])
    expect(resolveRoutes('http://127.0.0.1:3200', 'home=/,products=/products')).toEqual([
      { name: 'home', path: '/', url: 'http://127.0.0.1:3200/' },
      { name: 'products', path: '/products', url: 'http://127.0.0.1:3200/products' },
    ])
  })

  it('rejects invalid or duplicate route labels', () => {
    expect(() => parseRouteConfig('home=products')).toThrow('Invalid LIGHTHOUSE_ROUTES entry')
    expect(() => parseRouteConfig('home=/,home=/products')).toThrow('must be unique')
  })

  it('adds CI provenance and route-level deltas to the report', () => {
    const run = createRunMetadata({
      ...process.env,
      CI: 'true',
      GITHUB_SHA: 'commit-b',
      GITHUB_REF_NAME: 'master',
      GITHUB_REPOSITORY: 'owner/repo',
      GITHUB_RUN_ID: '42',
      GITHUB_RUN_ATTEMPT: '3',
      GITHUB_WORKFLOW: 'Frontend CI',
      GITHUB_EVENT_NAME: 'push',
    }, new Date('2026-07-26T12:00:00.000Z'))
    const previous = makeRecord('commit-a', '2026-07-25T12:00:00.000Z')
    const current = makeRecord('commit-b', '2026-07-26T12:00:00.000Z', {
      run,
      metrics: {
        ...previous.metrics,
        performanceScore: 88,
        largestContentfulPaint: 2400,
      },
    })

    const report = buildTrendReport({
      run,
      routeRecords: [current],
      history: [previous],
    })

    expect(report.run).toMatchObject({
      commitSha: 'commit-b',
      ref: 'master',
      repository: 'owner/repo',
      runId: '42',
      environment: 'ci',
    })
    expect(report.routes[0].comparison).toEqual({
      previousCommitSha: 'commit-a',
      previousTimestamp: '2026-07-25T12:00:00.000Z',
      deltas: expect.objectContaining({
        performanceScore: -2,
        largestContentfulPaint: 400,
      }),
    })
    expect(report.history.entries).toHaveLength(2)
  })

  it('replaces a duplicate commit and route record with its latest result', () => {
    const first = makeRecord('commit-a', '2026-07-25T12:00:00.000Z')
    const rerun = makeRecord('commit-a', '2026-07-25T13:00:00.000Z', {
      metrics: {
        ...first.metrics,
        performanceScore: 91,
      },
    })

    const history = mergeHistory([first], [rerun])

    expect(history).toHaveLength(1)
    expect(history[0]).toMatchObject({
      timestamp: '2026-07-25T13:00:00.000Z',
      metrics: { performanceScore: 91 },
    })
  })
})
