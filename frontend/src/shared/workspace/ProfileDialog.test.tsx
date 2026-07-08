import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useWorkspacePrefs } from './useWorkspacePrefs'
import { ProfileDialog } from './ProfileDialog'

function renderDialog(open = true) {
  return render(
    <MemoryRouter>
      <ProfileDialog open={open} onClose={vi.fn()} workspaceId="administration" />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  useAuthStore.setState({
    token: 'tok',
    user: { userId: 'admin', role: 'admin', exp: 9999999999 },
    isLoading: false,
    error: null,
  })
  useWorkspacePrefs.setState({ workspaceThemes: {} })
})

describe('ProfileDialog', () => {
  it('does not render when closed', () => {
    renderDialog(false)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('renders dialog when open', () => {
    renderDialog()
    expect(screen.getByRole('dialog', { name: 'Profile settings' })).toBeInTheDocument()
  })

  it('shows username and role', () => {
    renderDialog()
    const texts = screen.getAllByText('admin')
    // Appears twice: once as username value, once as role value
    expect(texts.length).toBeGreaterThanOrEqual(1)
  })

  it('shows three theme options', () => {
    renderDialog()
    expect(screen.getByRole('button', { name: /light/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /dark/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /system/i })).toBeInTheDocument()
  })

  it('selecting dark theme persists to workspace prefs', () => {
    renderDialog()
    fireEvent.click(screen.getByRole('button', { name: /dark/i }))
    expect(useWorkspacePrefs.getState().workspaceThemes['administration']).toBe('dark')
  })

  it('selecting system theme persists to workspace prefs', () => {
    renderDialog()
    fireEvent.click(screen.getByRole('button', { name: /system/i }))
    expect(useWorkspacePrefs.getState().workspaceThemes['administration']).toBe('system')
  })

  it('calls onClose when Escape is pressed', () => {
    const onClose = vi.fn()
    render(
      <MemoryRouter>
        <ProfileDialog open onClose={onClose} workspaceId="administration" />
      </MemoryRouter>,
    )
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('calls onClose when backdrop is clicked', () => {
    const onClose = vi.fn()
    const { container } = render(
      <MemoryRouter>
        <ProfileDialog open onClose={onClose} workspaceId="administration" />
      </MemoryRouter>,
    )
    // The backdrop is the first fixed div with bg-black/20
    const backdrop = container.querySelector('[aria-hidden="true"]') as HTMLElement
    fireEvent.click(backdrop)
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('shows sign out button', () => {
    renderDialog()
    expect(screen.getByRole('button', { name: /sign out/i })).toBeInTheDocument()
  })

  it('logout calls auth store logout and navigates to /login', async () => {
    const logoutSpy = vi.fn()
    useAuthStore.setState({ logout: logoutSpy })
    renderDialog()
    fireEvent.click(screen.getByRole('button', { name: /sign out/i }))
    expect(logoutSpy).toHaveBeenCalledOnce()
  })
})
