import { useEffect, useState, type ReactNode } from 'react'
import { Sun, Moon } from 'lucide-react'
import { useWorkspacePrefs, type WorkspaceTheme } from './useWorkspacePrefs'

export type WorkspaceId =
  | 'operator'
  | 'investigation'
  | 'playback'
  | 'administration'
  | 'analytics'
  | 'maintenance'

interface WorkspaceShellProps {
  workspaceId: WorkspaceId
  toolbar?: ReactNode
  children: ReactNode
  defaultTheme?: WorkspaceTheme
}

function useSystemTheme(): 'light' | 'dark' {
  const [sys, setSys] = useState<'light' | 'dark'>(() =>
    typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light',
  )
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setSys(e.matches ? 'dark' : 'light')
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  return sys
}

export function WorkspaceShell({
  workspaceId,
  toolbar,
  children,
  defaultTheme = 'light',
}: WorkspaceShellProps) {
  const storedTheme = useWorkspacePrefs((s) => s.workspaceThemes[workspaceId])
  const setWorkspaceTheme = useWorkspacePrefs((s) => s.setWorkspaceTheme)
  const systemTheme = useSystemTheme()

  const isOperator = workspaceId === 'operator'
  const pref: WorkspaceTheme = isOperator ? 'dark' : (storedTheme ?? defaultTheme)
  const resolvedTheme: 'light' | 'dark' = pref === 'system' ? systemTheme : pref

  function toggleTheme() {
    setWorkspaceTheme(workspaceId, resolvedTheme === 'dark' ? 'light' : 'dark')
  }

  return (
    <div
      data-workspace-id={workspaceId}
      data-theme={resolvedTheme}
      className="contents"
    >
      {!isOperator && (
        <div className="sr-only">
          <button
            type="button"
            aria-label="Toggle theme"
            onClick={toggleTheme}
          >
            {resolvedTheme === 'dark' ? (
              <Sun className="h-4 w-4" aria-hidden="true" />
            ) : (
              <Moon className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        </div>
      )}
      {toolbar}
      {children}
    </div>
  )
}
