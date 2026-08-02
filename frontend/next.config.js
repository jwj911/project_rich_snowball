/**
 * @type {import('next').NextConfig}
 *
 * Bundle Budget 基线（2026-05-25）：
 * - Shared JS:   ~87 kB
 * - /products:   ~124 kB FLJS
 * - /products/[id]: ~135 kB FLJS
 * 红线：任意路由 First Load JS 不得超过 180 kB。
 */
const withBundleAnalyzer = require('@next/bundle-analyzer')({
  enabled: process.env.ANALYZE === 'true',
})
const {
  DEFAULT_API_BASE,
  buildCspHeaders,
} = require('./config/security-headers')

const API_BASE = process.env.NEXT_PUBLIC_API_BASE || DEFAULT_API_BASE
const CSP_HEADERS = buildCspHeaders({
  apiBase: API_BASE,
  reportUrl: process.env.CSP_REPORT_URL,
})

const nextConfig = {
  reactStrictMode: true,
  output: 'standalone',
  poweredByHeader: false,
  compress: true,
  images: {
    unoptimized: true,
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          {
            key: 'X-Content-Type-Options',
            value: 'nosniff',
          },
          {
            key: 'X-Frame-Options',
            value: 'DENY',
          },
          {
            key: 'Referrer-Policy',
            value: 'strict-origin-when-cross-origin',
          },
          {
            key: 'Permissions-Policy',
            value: 'camera=(), microphone=(), geolocation=(), interest-cohort=()',
          },
          ...CSP_HEADERS,
        ],
      },
    ]
  },
}

module.exports = withBundleAnalyzer(nextConfig)
