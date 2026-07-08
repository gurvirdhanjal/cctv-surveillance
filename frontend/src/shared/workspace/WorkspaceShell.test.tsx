import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { useWorkspacePrefs } from './useWorkspacePrefs'
import { WorkspaceShell } from './WorkspaceShell'

beforeEach(() => {
  useWorkspacePrefs.setState({
    workspaceThemes: {},
    version: 1,
    tableLayouts: {},
    sidebarOpen: true,
    favoriteCameraIds: [],
    defaultGridLayout: '2x2',
    recentCameraIds: [],
    pinnedAlertIds: [],
    treeExpansion: {},
    treeOrder: {},
    cmdkRecents: [],
    panelLayouts: {},
  })
})

describe('WorkspaceShell', () => {
  it('renders data-workspace-id attribute', () => {
    const { container } = render(
      <WorkspaceShell workspaceId="administration">
        <span>content</span>
      </WorkspaceShell>,
    )
    expect(container.firstChild).toHaveAttribute('data-workspace-id', 'administration')
  })

  it('operator workspace forces data-theme="dark"', () => {
    const { container } = render(
      <WorkspaceShell workspaceId="operator">
        <span>live</span>
      </WorkspaceShell>,
    )
    expect(container.firstChild).toHaveAttribute('data-theme', 'dark')
  })

  it('operator workspace hides theme toggle', () => {
    render(
      <WorkspaceShell workspaceId="operator">
        <span>live</span>
      </WorkspaceShell>,
    )
    expect(screen.queryByRole('button', { name: /toggle theme/i })).not.toBeInTheDocument()
  })

  it('non-operator workspace shows theme toggle', () => {
    render(
      <WorkspaceShell workspaceId="analytics">
        <span>analytics</span>
      </WorkspaceShell>,
    )
    expect(screen.getByRole('button', { name: /toggle theme/i })).toBeInTheDocument()
  })

  it('theme toggle persists to workspaceThemes slice', () => {
    render(
      <WorkspaceShell workspaceId="analytics">
        <span>analytics</span>
      </WorkspaceShell>,
    )
    const toggle = screen.getByRole('button', { name: /toggle theme/i })
    fireEvent.click(toggle)
    const stored = useWorkspacePrefs.getState().workspaceThemes['analytics']
    expect(['light', 'dark']).toContain(stored)
  })

  it('switching workspaceId does not reset another workspace theme', () => {
    useWorkspacePrefs.setState({
      workspaceThemes: { analytics: 'dark' },
    })
    render(
      <WorkspaceShell workspaceId="investigation">
        <span>forensic</span>
      </WorkspaceShell>,
    )
    expect(useWorkspacePrefs.getState().workspaceThemes['analytics']).toBe('dark')
  })

  it('applies data-theme from persisted prefs for non-operator', () => {
    useWorkspacePrefs.setState({
      workspaceThemes: { administration: 'dark' },
    })
    const { container } = render(
      <WorkspaceShell workspaceId="administration">
        <span>admin</span>
      </WorkspaceShell>,
    )
    expect(container.firstChild).toHaveAttribute('data-theme', 'dark')
  })

  it('renders children', () => {
    render(
      <WorkspaceShell workspaceId="administration">
        <p>child content</p>
      </WorkspaceShell>,
    )
    expect(screen.getByText('child content')).toBeInTheDocument()
  })
})
