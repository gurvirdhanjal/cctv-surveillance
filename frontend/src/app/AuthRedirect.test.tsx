import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { AuthRedirect, UNAUTHORIZED_EVENT } from './AuthRedirect'
import { useAuthStore } from '@/stores/authStore'

function renderWithRouter(initialPath = '/guard') {
  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <AuthRedirect />
        <Routes>
          <Route path="/login" element={<div>login page</div>} />
          <Route path="/guard" element={<div>guard page</div>} />
        </Routes>
      </MemoryRouter>
    </HelmetProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState({ token: null, user: null, isLoading: false, error: null })
})

describe('AuthRedirect', () => {
  it('hydrates auth store from localStorage on mount', () => {
    const token =
      'header.' +
      btoa(JSON.stringify({ sub: '1', role: 'admin', exp: 9_999_999_999 })).replace(/=/g, '') +
      '.sig'
    localStorage.setItem('vms-auth', JSON.stringify({ token }))

    renderWithRouter()

    expect(useAuthStore.getState().token).toBe(token)
    expect(useAuthStore.getState().user?.role).toBe('admin')
  })

  it('redirects to /login on vms:unauthorized event', async () => {
    renderWithRouter('/guard')
    expect(screen.getByText('guard page')).toBeInTheDocument()

    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))

    await waitFor(() => {
      expect(screen.getByText('login page')).toBeInTheDocument()
    })
  })

  it('clears token on unauthorized redirect', async () => {
    const token =
      'header.' +
      btoa(JSON.stringify({ sub: '1', role: 'guard', exp: 9_999_999_999 })).replace(/=/g, '') +
      '.sig'
    useAuthStore.setState({ token, user: { userId: '1', role: 'guard', exp: 9_999_999_999 } })

    renderWithRouter('/guard')
    window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT))

    await waitFor(() => {
      expect(useAuthStore.getState().token).toBeNull()
    })
  })
})
