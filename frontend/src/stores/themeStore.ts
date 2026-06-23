import { create } from 'zustand'

type Theme = 'light' | 'dark'
const STORAGE_KEY = 'vms-theme'

interface ThemeState {
  theme: Theme
  /** User action — writes to localStorage and updates data-theme. */
  toggleTheme: () => void
  /** Route override — applies theme WITHOUT writing to localStorage. */
  applyTheme: (t: Theme) => void
}

function getInitialTheme(): Theme {
  if (typeof window === 'undefined') return 'light'
  return (localStorage.getItem(STORAGE_KEY) as Theme | null) ?? 'light'
}

export const useThemeStore = create<ThemeState>((set) => ({
  theme: getInitialTheme(),

  toggleTheme: () =>
    set((s) => {
      const next: Theme = s.theme === 'light' ? 'dark' : 'light'
      localStorage.setItem(STORAGE_KEY, next)
      document.documentElement.setAttribute('data-theme', next)
      return { theme: next }
    }),

  applyTheme: (t: Theme) => {
    document.documentElement.setAttribute('data-theme', t)
    set({ theme: t })
  },
}))
