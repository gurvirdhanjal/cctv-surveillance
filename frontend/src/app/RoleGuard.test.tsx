import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { RoleGuard } from './RoleGuard'
import { useAuthStore } from '@/stores/authStore'

// Token helpers — only payload matters for client-side decode
function makeToken(role: string) {
  const payload = btoa(JSON.stringify({ sub: '1', role, exp: 9_999_999_999 })).replace(/=/g, '')
  return `header.${payload}.sig`
}

function renderWithAuth(role: string | null, path: string) {
  if (role) {
    useAuthStore.setState({
      token: makeToken(role),
      user: { userId: '1', role: role as never, exp: 9_999_999_999 },
      isLoading: false,
      error: null,
    })
  }

  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/login" element={<div>login page</div>} />
          <Route path="/403" element={<div>forbidden page</div>} />
          <Route
            path="/analytics"
            element={
              <RoleGuard allow={['manager', 'admin']}>
                <div>analytics page</div>
              </RoleGuard>
            }
          />
          <Route
            path="/admin"
            element={
              <RoleGuard allow={['admin']}>
                <div>admin page</div>
              </RoleGuard>
            }
          />
          <Route
            path="/guard"
            element={
              <RoleGuard allow={['guard', 'manager', 'admin']}>
                <div>guard page</div>
              </RoleGuard>
            }
          />
        </Routes>
      </MemoryRouter>
    </HelmetProvider>,
  )
}

beforeEach(() => {
  useAuthStore.setState({ token: null, user: null, isLoading: false, error: null })
})

describe('RoleGuard', () => {
  it('redirects unauthenticated users to /login with ?next=', () => {
    renderWithAuth(null, '/analytics')
    expect(screen.getByText('login page')).toBeInTheDocument()
  })

  it('allows admin to access /analytics', () => {
    renderWithAuth('admin', '/analytics')
    expect(screen.getByText('analytics page')).toBeInTheDocument()
  })

  it('allows manager to access /analytics', () => {
    renderWithAuth('manager', '/analytics')
    expect(screen.getByText('analytics page')).toBeInTheDocument()
  })

  it('blocks guard from /analytics → redirects to /403', () => {
    renderWithAuth('guard', '/analytics')
    expect(screen.getByText('forbidden page')).toBeInTheDocument()
  })

  it('blocks manager from /admin → redirects to /403', () => {
    renderWithAuth('manager', '/admin')
    expect(screen.getByText('forbidden page')).toBeInTheDocument()
  })

  it('allows admin to access /admin', () => {
    renderWithAuth('admin', '/admin')
    expect(screen.getByText('admin page')).toBeInTheDocument()
  })

  it('allows guard to access /guard', () => {
    renderWithAuth('guard', '/guard')
    expect(screen.getByText('guard page')).toBeInTheDocument()
  })
})
