const DEFAULT_API_BASE = 'http://127.0.0.1:8401'
const CSP_REPORT_PATH = '/api/log/csp-report'
const CSP_REPORTING_GROUP = 'csp-report'

/**
 * @typedef {object} CspOptions
 * @property {string} [apiBase]
 * @property {string} [reportUrl]
 */

function parseSafeHttpUrl(rawValue, label) {
  if (typeof rawValue !== 'string' || !rawValue || rawValue !== rawValue.trim()) {
    throw new Error(`${label} must be a non-empty absolute URL without surrounding whitespace`)
  }
  if (/[\u0000-\u0020\u007f\\;,"]/u.test(rawValue)) {
    throw new Error(`${label} contains characters that are unsafe in response headers`)
  }

  let url
  try {
    url = new URL(rawValue)
  } catch {
    throw new Error(`${label} must be an absolute HTTP(S) URL`)
  }

  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new Error(`${label} must use http or https`)
  }
  if (url.username || url.password) {
    throw new Error(`${label} must not include credentials`)
  }
  if (url.search || url.hash) {
    throw new Error(`${label} must not include a query string or fragment`)
  }

  return url
}

/**
 * @param {CspOptions} [options]
 */
function resolveCspReportUrl({
  apiBase = DEFAULT_API_BASE,
  reportUrl,
} = {}) {
  if (reportUrl !== undefined) {
    return parseSafeHttpUrl(reportUrl, 'CSP_REPORT_URL').toString()
  }

  const apiUrl = parseSafeHttpUrl(apiBase, 'NEXT_PUBLIC_API_BASE')
  return new URL(CSP_REPORT_PATH, apiUrl.origin).toString()
}

function buildEnforcedCsp(apiBase = DEFAULT_API_BASE) {
  parseSafeHttpUrl(apiBase, 'NEXT_PUBLIC_API_BASE')
  return [
    "default-src 'self'",
    "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data:",
    `connect-src 'self' ${apiBase}`,
    "font-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
  ].join('; ')
}

/**
 * @param {CspOptions} [options]
 */
function buildReportOnlyCsp({
  apiBase = DEFAULT_API_BASE,
  reportUrl,
} = {}) {
  const safeReportUrl = resolveCspReportUrl({ apiBase, reportUrl })
  return [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' blob: data:",
    `connect-src 'self' ${apiBase}`,
    "font-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    `report-uri ${safeReportUrl}`,
    `report-to ${CSP_REPORTING_GROUP}`,
  ].join('; ')
}

/**
 * @param {CspOptions} [options]
 */
function buildCspHeaders({
  apiBase = DEFAULT_API_BASE,
  reportUrl,
} = {}) {
  const safeReportUrl = resolveCspReportUrl({ apiBase, reportUrl })
  return [
    {
      key: 'Content-Security-Policy',
      value: buildEnforcedCsp(apiBase),
    },
    {
      key: 'Content-Security-Policy-Report-Only',
      value: buildReportOnlyCsp({ apiBase, reportUrl: safeReportUrl }),
    },
    {
      key: 'Reporting-Endpoints',
      value: `${CSP_REPORTING_GROUP}="${safeReportUrl}"`,
    },
  ]
}

module.exports = {
  CSP_REPORTING_GROUP,
  DEFAULT_API_BASE,
  buildCspHeaders,
  buildEnforcedCsp,
  buildReportOnlyCsp,
  resolveCspReportUrl,
}
