import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  // Use VMS data-theme attribute so shadcn dark: utilities align with our theme system
  darkMode: ['selector', '[data-theme="dark"]'],
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
          50:  '#fef9f0',
          100: '#fdf3e3',
          200: '#f0d8a8',
          300: '#d4a855',
          // brand-500 uses RGB channel variable so opacity modifiers (bg-brand-500/10) work
          500: 'rgb(var(--brand-accent-rgb) / <alpha-value>)',
          600: '#8f611f',
          700: '#8f611f',
          900: '#744e19',
          950: '#2a2013',
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
