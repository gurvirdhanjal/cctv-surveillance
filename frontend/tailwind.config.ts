import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  // Use VMS data-theme attribute so shadcn dark: utilities align with our theme system
  darkMode: ['selector', '[data-theme="dark"]', 'class'],
  theme: {
  	extend: {
  		fontFamily: {
  			display: [
  				'var(--font-display)'
  			],
  			body: [
  				'var(--font-body)'
  			],
  			mono: [
  				'var(--font-mono)'
  			]
  		},
  		colors: {
  			text: {
  				primary: 'var(--text-primary)',
  				secondary: 'var(--text-secondary)',
  				muted: 'var(--text-muted)',
  				inverse: 'var(--text-inverse)'
  			},
  			surface: {
  				base: 'var(--surface-base)',
  				raised: 'var(--surface-raised)',
  				sunken: 'var(--surface-sunken)'
  			},
  			border: {
  				DEFAULT: 'var(--border-default)',
  				strong: 'var(--border-strong)'
  			},
  			severity: {
  				critical: 'var(--severity-critical)',
  				high: 'var(--severity-high)',
  				medium: 'var(--severity-medium)',
  				low: 'var(--severity-low)'
  			},
  			brand: {
  				'50': '#fef9f0',
  				'100': '#fdf3e3',
  				'200': '#f0d8a8',
  				'300': '#d4a855',
  				'500': 'rgb(var(--brand-accent-rgb) / <alpha-value>)',
  				'600': '#8f611f',
  				'700': '#8f611f',
  				'900': '#744e19',
  				'950': '#2a2013'
  			},
  			action: {
  				'600': '#334155',
  				'700': '#1e293b',
  				'800': '#0f172a',
  				'900': '#020617'
  			},
  			status: {
  				online: 'var(--status-online)',
  				offline: 'var(--status-offline)',
  				'auth-failed': 'var(--status-auth-failed)',
  				maintenance: 'var(--status-maintenance)'
  			},
  			interactive: {
  				primary: 'var(--interactive-primary)',
  				hover: 'var(--interactive-hover)',
  				active: 'var(--interactive-active)'
  			},
  			focus: {
  				ring: 'var(--focus-ring)'
  			},
  			success: 'var(--success)',
  			info: 'var(--info)',
  			warning: 'var(--warning)',
  			error: 'var(--error)',
  			destructive: 'var(--destructive)',
  			sidebar: {
  				DEFAULT: 'var(--sidebar-background)',
  				foreground: 'var(--sidebar-foreground)',
  				primary: 'var(--sidebar-primary)',
  				'primary-foreground': 'var(--sidebar-primary-foreground)',
  				accent: 'var(--sidebar-accent)',
  				'accent-foreground': 'var(--sidebar-accent-foreground)',
  				border: 'var(--sidebar-border)',
  				ring: 'var(--sidebar-ring)'
  			}
  		},
  		boxShadow: {
  			'1': 'var(--shadow-1)',
  			'2': 'var(--shadow-2)',
  			'3': 'var(--shadow-3)',
  			'4': 'var(--shadow-4)'
  		},
  		borderRadius: {
  			xs: 'var(--radius-xs)',
  			sm: 'var(--radius-sm)',
  			md: 'var(--radius-md)',
  			lg: 'var(--radius-lg)',
  			xl: 'var(--radius-xl)',
  			'2xl': 'var(--radius-2xl)',
  			full: 'var(--radius-full)'
  		},
  		transitionDuration: {
  			fast: 'var(--duration-fast)',
  			quick: 'var(--duration-quick)',
  			base: 'var(--duration-base)',
  			slow: 'var(--duration-slow)',
  			'dur-fast': 'var(--dur-fast)',
  			'dur-normal': 'var(--dur-normal)',
  			'dur-slow': 'var(--dur-slow)',
  			'dur-xslow': 'var(--dur-xslow)'
  		},
  		zIndex: {
  			raised: '1',
  			selected: '2',
  			toolbar: '40',
  			modal: '50',
  			cmdk: '60',
  			toast: '70'
  		}
  	}
  },
  plugins: [],
}

export default config
