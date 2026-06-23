import { useEffect } from 'react'
import { useThemeStore } from '@/stores/themeStore'

const STORAGE_KEY = 'vms-theme'

/** Apply a theme for the lifetime of a route without persisting it to localStorage. */
export function useRouteTheme(forced: 'light' | 'dark') {
  const apply = useThemeStore((s) => s.applyTheme)
  const stored = (localStorage.getItem(STORAGE_KEY) as 'light' | 'dark') ?? 'light'

  useEffect(() => {
    apply(forced)
    return () => apply(stored)
  }, [forced, apply, stored])
}
