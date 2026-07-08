import type { ReactNode } from 'react'
import { Sun, Moon } from 'lucide-react'
import { useWorkspacePrefs } from './useWorkspacePrefs'

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
  defaultTheme?: 'light' | 'dark'
}

export function WorkspaceShell({
  workspaceId,
  toolbar,
  children,
  defaultTheme = 'light',
}: WorkspaceShellProps) {
  const storedTheme = useWorkspacePrefs((s) => s.workspaceThemes[workspaceId])
  const setWorkspaceTheme = useWorkspacePrefs((s) => s.setWorkspaceTheme)

  const isOperator = workspaceId === 'operator'
  const theme = isOperator ? 'dark' : (storedTheme ?? defaultTheme)

  function toggleTheme() {
    setWorkspaceTheme(workspaceId, theme === 'dark' ? 'light' : 'dark')
  }

  return (
    <div
      data-workspace-id={workspaceId}
      data-theme={theme}
      className="contents"
    >
      {!isOperator && (
        <div className="sr-only">
          <button
            type="button"
            aria-label="Toggle theme"
            onClick={toggleTheme}
          >
            {theme === 'dark' ? (
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
