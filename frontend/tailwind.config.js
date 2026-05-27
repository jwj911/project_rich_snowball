/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        up: '#ef4444',
        down: '#22c55e',
        card: '#1e293b',
        background: '#0f172a',
        surface: {
          DEFAULT: '#10161d',
          elevated: '#1e222d',
          inset: '#131722',
        },
        border: {
          DEFAULT: '#2a2e39',
        },
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
