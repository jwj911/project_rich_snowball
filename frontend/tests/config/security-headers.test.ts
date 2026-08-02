// @vitest-environment node

import { describe, expect, it } from 'vitest'
import {
  buildCspHeaders,
  buildEnforcedCsp,
  buildReportOnlyCsp,
  resolveCspReportUrl,
} from '../../config/security-headers.js'

const API_BASE = 'https://api.example.test'
const ORIGINAL_ENFORCED_CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' blob: data:",
  `connect-src 'self' ${API_BASE}`,
  "font-src 'self'",
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join('; ')

function parseDirectives(policy: string) {
  return new Map(policy.split('; ').map((directive) => {
    const [name, ...values] = directive.split(' ')
    return [name, values]
  }))
}

describe('CSP security headers', () => {
  it('keeps the enforced CSP value unchanged', () => {
    expect(buildEnforcedCsp(API_BASE)).toBe(ORIGINAL_ENFORCED_CSP)
  })

  it('adds report-only and reporting endpoint headers without replacing enforcement', () => {
    const headers = buildCspHeaders({ apiBase: API_BASE })
    const byName = new Map(headers.map(({ key, value }) => [key, value]))

    expect(byName.get('Content-Security-Policy')).toBe(ORIGINAL_ENFORCED_CSP)
    expect(byName.get('Content-Security-Policy-Report-Only')).toBe(
      buildReportOnlyCsp({ apiBase: API_BASE }),
    )
    expect(byName.get('Reporting-Endpoints')).toBe(
      'csp-report="https://api.example.test/api/log/csp-report"',
    )
  })

  it('only tightens script-src while retaining current runtime boundaries', () => {
    const enforced = parseDirectives(buildEnforcedCsp(API_BASE))
    const reportOnly = parseDirectives(buildReportOnlyCsp({ apiBase: API_BASE }))

    expect(reportOnly.get('script-src')).toEqual(["'self'"])
    expect(reportOnly.get('script-src')).not.toContain("'unsafe-inline'")
    expect(reportOnly.get('script-src')).not.toContain("'unsafe-eval'")

    for (const name of [
      'default-src',
      'style-src',
      'img-src',
      'connect-src',
      'font-src',
      'frame-ancestors',
      'base-uri',
      'form-action',
    ]) {
      expect(reportOnly.get(name), name).toEqual(enforced.get(name))
    }
    expect(reportOnly.get('report-uri')).toEqual([
      'https://api.example.test/api/log/csp-report',
    ])
    expect(reportOnly.get('report-to')).toEqual(['csp-report'])
  })

  it('builds the default report URL from the API origin', () => {
    expect(resolveCspReportUrl({
      apiBase: 'https://api.example.test/v1',
    })).toBe('https://api.example.test/api/log/csp-report')
  })

  it('accepts a controlled absolute HTTP(S) report URL override', () => {
    expect(resolveCspReportUrl({
      apiBase: API_BASE,
      reportUrl: 'https://reports.example.test/csp',
    })).toBe('https://reports.example.test/csp')
    expect(resolveCspReportUrl({
      apiBase: API_BASE,
      reportUrl: 'http://127.0.0.1:8401/api/log/csp-report',
    })).toBe('http://127.0.0.1:8401/api/log/csp-report')
  })

  it.each([
    ['relative URL', '/api/log/csp-report'],
    ['unsupported protocol', 'ftp://reports.example.test/csp'],
    ['credentials', 'https://user:secret@reports.example.test/csp'],
    ['query string', 'https://reports.example.test/csp?token=secret'],
    ['fragment', 'https://reports.example.test/csp#secret'],
    ['surrounding whitespace', ' https://reports.example.test/csp'],
    ['header injection', 'https://reports.example.test/csp\r\nX-Test: injected'],
    ['CSP directive separator', 'https://reports.example.test/csp;script-src'],
    ['structured header delimiter', 'https://reports.example.test/csp,other'],
    ['quoted header value', 'https://reports.example.test/csp"'],
    ['backslash normalization', 'https://reports.example.test\\csp'],
  ])('rejects an unsafe report override containing %s', (_case, reportUrl) => {
    expect(() => resolveCspReportUrl({ apiBase: API_BASE, reportUrl })).toThrow()
  })

  it.each([
    'relative-api',
    'ftp://api.example.test',
    'https://user:secret@api.example.test',
    'https://api.example.test?token=secret',
    'https://api.example.test#secret',
  ])('rejects an unsafe API base used to derive the default report URL', (apiBase) => {
    expect(() => resolveCspReportUrl({ apiBase })).toThrow()
    expect(() => buildEnforcedCsp(apiBase)).toThrow()
  })
})
