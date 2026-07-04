/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Semantic page tokens (Vercel Geist Dark)
        background: '#000000',
        foreground: '#ededed',
        muted: '#a0a0a0',
        accent: '#006efe',

        // Gray solid scale
        'gray-100': '#1a1a1a',
        'gray-200': '#1f1f1f',
        'gray-300': '#292929',
        'gray-400': '#2e2e2e',
        'gray-500': '#454545',
        'gray-600': '#878787',
        'gray-700': '#8f8f8f',
        'gray-800': '#7d7d7d',
        'gray-900': '#a0a0a0',
        'gray-1000': '#ededed',

        // Gray translucent scale
        'gray-alpha-100': '#ffffff12',
        'gray-alpha-200': '#ffffff17',
        'gray-alpha-300': '#ffffff21',
        'gray-alpha-400': '#ffffff24',
        'gray-alpha-500': '#ffffff3d',
        'gray-alpha-600': '#ffffff82',
        'gray-alpha-700': '#ffffff8a',
        'gray-alpha-800': '#ffffff78',
        'gray-alpha-900': '#ffffff9c',
        'gray-alpha-1000': '#ffffffeb',

        // Blue
        'blue-100': '#06193a',
        'blue-200': '#022248',
        'blue-300': '#002f62',
        'blue-400': '#003674',
        'blue-500': '#00418b',
        'blue-600': '#0090ff',
        'blue-700': '#006efe',
        'blue-800': '#005be7',
        'blue-900': '#47a8ff',
        'blue-1000': '#eaf6ff',

        // Red
        'red-100': '#330a11',
        'red-200': '#440d13',
        'red-300': '#5d0e17',
        'red-400': '#6f101b',
        'red-500': '#88151f',
        'red-600': '#f32e40',
        'red-700': '#f13242',
        'red-800': '#e2162a',
        'red-900': '#ff565f',
        'red-1000': '#ffe9ed',

        // Amber
        'amber-100': '#2a1700',
        'amber-200': '#361900',
        'amber-300': '#502800',
        'amber-400': '#5b3000',
        'amber-500': '#703e00',
        'amber-600': '#ed9a00',
        'amber-700': '#ffae00',
        'amber-800': '#ff9300',
        'amber-900': '#ff9300',
        'amber-1000': '#fff3d5',

        // Green
        'green-100': '#002608',
        'green-200': '#00320b',
        'green-300': '#003a0e',
        'green-400': '#004615',
        'green-500': '#006717',
        'green-600': '#00952d',
        'green-700': '#00ac3a',
        'green-800': '#009432',
        'green-900': '#00ca50',
        'green-1000': '#d8ffe4',

        // Teal
        'teal-100': '#00231b',
        'teal-200': '#002b22',
        'teal-300': '#003d34',
        'teal-400': '#004035',
        'teal-500': '#006354',
        'teal-600': '#009e86',
        'teal-700': '#00aa95',
        'teal-800': '#00927f',
        'teal-900': '#00cfb7',
        'teal-1000': '#cbfff5',

        // Purple
        'purple-100': '#290c33',
        'purple-200': '#341142',
        'purple-300': '#47185e',
        'purple-400': '#541a76',
        'purple-500': '#642290',
        'purple-600': '#9440d5',
        'purple-700': '#9440d5',
        'purple-800': '#7d2bba',
        'purple-900': '#c472fb',
        'purple-1000': '#fbecff',

        // Pink
        'pink-100': '#310d1e',
        'pink-200': '#420c25',
        'pink-300': '#571032',
        'pink-400': '#5d0c34',
        'pink-500': '#76063f',
        'pink-600': '#ba0056',
        'pink-700': '#f12b82',
        'pink-800': '#e7006d',
        'pink-900': '#ff4d8d',
        'pink-1000': '#ffe9f4',

        // Market semantics (China convention)
        up: '#f13242',
        down: '#00ac3a',

        // Legacy aliases for backward compatibility during migration
        card: '#1a1a1a',
        surface: {
          DEFAULT: '#000000',
          elevated: '#1a1a1a',
          inset: '#111111',
        },
        border: {
          DEFAULT: '#ffffff24',
        },
      },
      fontFamily: {
        sans: ['var(--font-geist-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-geist-mono)', 'monospace'],
      },
      borderRadius: {
        sm: '6px',
        DEFAULT: '6px',
        md: '12px',
        lg: '16px',
      },
      boxShadow: {
        raised: '0 1px 2px rgba(0, 0, 0, 0.16)',
        popover:
          '0 1px 1px rgba(0, 0, 0, 0.02), 0 4px 8px -4px rgba(0, 0, 0, 0.04), 0 16px 24px -8px rgba(0, 0, 0, 0.06)',
        modal:
          '0 1px 1px rgba(0, 0, 0, 0.02), 0 8px 16px -4px rgba(0, 0, 0, 0.04), 0 24px 32px -8px rgba(0, 0, 0, 0.06)',
      },
      fontSize: {
        'heading-72': ['72px', { lineHeight: '72px', letterSpacing: '-4.32px', fontWeight: '600' }],
        'heading-64': ['64px', { lineHeight: '64px', letterSpacing: '-3.84px', fontWeight: '600' }],
        'heading-56': ['56px', { lineHeight: '56px', letterSpacing: '-3.36px', fontWeight: '600' }],
        'heading-48': ['48px', { lineHeight: '56px', letterSpacing: '-2.88px', fontWeight: '600' }],
        'heading-40': ['40px', { lineHeight: '48px', letterSpacing: '-2.4px', fontWeight: '600' }],
        'heading-32': ['32px', { lineHeight: '40px', letterSpacing: '-1.28px', fontWeight: '600' }],
        'heading-24': ['24px', { lineHeight: '32px', letterSpacing: '-0.96px', fontWeight: '600' }],
        'heading-20': ['20px', { lineHeight: '26px', letterSpacing: '-0.4px', fontWeight: '600' }],
        'heading-16': ['16px', { lineHeight: '24px', letterSpacing: '-0.32px', fontWeight: '600' }],
        'heading-14': ['14px', { lineHeight: '20px', letterSpacing: '-0.28px', fontWeight: '600' }],
        'copy-24': ['24px', { lineHeight: '36px', fontWeight: '400' }],
        'copy-20': ['20px', { lineHeight: '36px', fontWeight: '400' }],
        'copy-18': ['18px', { lineHeight: '28px', fontWeight: '400' }],
        'copy-16': ['16px', { lineHeight: '24px', fontWeight: '400' }],
        'copy-14': ['14px', { lineHeight: '20px', fontWeight: '400' }],
        'copy-13': ['13px', { lineHeight: '18px', fontWeight: '400' }],
        'label-20': ['20px', { lineHeight: '32px', fontWeight: '400' }],
        'label-18': ['18px', { lineHeight: '20px', fontWeight: '400' }],
        'label-16': ['16px', { lineHeight: '20px', fontWeight: '400' }],
        'label-14': ['14px', { lineHeight: '20px', fontWeight: '400' }],
        'label-13': ['13px', { lineHeight: '16px', fontWeight: '400' }],
        'label-12': ['12px', { lineHeight: '16px', fontWeight: '400' }],
      },
      transitionTimingFunction: {
        'vercel-pop': 'cubic-bezier(0.175, 0.885, 0.32, 1.1)',
      },
    },
  },
  plugins: [],
}
