import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['var(--font-display)'],
        body: ['var(--font-body)'],
        mono: ['var(--font-mono)'],
      },
      colors: {
        text: {
          primary: 'var(--text-primary)',
          secondary: 'var(--text-secondary)',
          muted: 'var(--text-muted)',
          inverse: 'var(--text-inverse)',
        },
        surface: {
          base: 'var(--surface-base)',
          raised: 'var(--surface-raised)',
          sunken: 'var(--surface-sunken)',
        },
        border: {
          DEFAULT: 'var(--border-default)',
          strong: 'var(--border-strong)',
        },
        severity: {
          critical: 'var(--severity-critical)',
          high: 'var(--severity-high)',
          medium: 'var(--severity-medium)',
          low: 'var(--severity-low)',
        },
        brand: {
          50:  '#fff1f0',
          100: '#ffe4e1',
          500: '#c0392b',
          700: '#9b2226',
          950: '#3b0a0a',
        },
        action: {
          600: '#334155',
          700: '#1e293b',
          800: '#0f172a',
          900: '#020617',
        },
        status: {
          online: 'var(--status-online)',
          offline: 'var(--status-offline)',
          'auth-failed': 'var(--status-auth-failed)',
          maintenance: 'var(--status-maintenance)',
        },
        success: 'var(--success)',
        info: 'var(--info)',
        warning: 'var(--warning)',
        error: 'var(--error)',
        destructive: 'var(--destructive)',
      },
      boxShadow: {
        1: 'var(--shadow-1)',
        2: 'var(--shadow-2)',
        3: 'var(--shadow-3)',
      },
      borderRadius: {
        sm: '4px',
        md: '6px',
        lg: '8px',
        xl: '12px',
      },
      transitionDuration: {
        fast:  'var(--duration-fast)',
        quick: 'var(--duration-quick)',
        base:  'var(--duration-base)',
        slow:  'var(--duration-slow)',
      },
    },
  },
  plugins: [],
}

export default config
