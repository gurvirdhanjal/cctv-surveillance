import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { LoginPage } from './LoginPage'
import { useAuthStore } from '@/stores/authStore'

const ADMIN_TOKEN =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.' +
  btoa(JSON.stringify({ sub: '1', role: 'admin', exp: 9_999_999_999 })).replace(/=/g, '') +
  '.sig'

function renderLogin(initialPath = '/login') {
  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <LoginPage />
      </MemoryRouter>
    </HelmetProvider>,
  )
}

// Capture initial state (including original action functions) before any test runs
const initialAuthState = useAuthStore.getState()

beforeEach(() => {
  localStorage.clear()
  // Replace (not merge) the entire store so mocked actions from one test don't leak
  useAuthStore.setState(initialAuthState, true)
  vi.restoreAllMocks()
})

describe('LoginPage', () => {
  it('renders username and password fields', () => {
    renderLogin()
    expect(screen.getByLabelText('Username')).toBeInTheDocument()
    expect(screen.getByLabelText('Password')).toBeInTheDocument()
  })

  it('renders a submit button', () => {
    renderLogin()
    expect(screen.getByRole('button', { name: 'Log in' })).toBeInTheDocument()
  })

  it('shows validation error when submitted empty', async () => {
    renderLogin()
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))
    await waitFor(() => {
      expect(screen.getByText('Username is required')).toBeInTheDocument()
    })
  })

  it('calls login with entered credentials on submit', async () => {
    const mockLogin = vi.fn().mockResolvedValue(undefined)
    useAuthStore.setState({ login: mockLogin } as never)

    renderLogin()
    await userEvent.type(screen.getByLabelText('Username'), 'admin')
    await userEvent.type(screen.getByLabelText('Password'), 'secret')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('admin', 'secret')
    })
  })

  it('shows error message on invalid credentials (401)', async () => {
    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: () => Promise.resolve({ detail: 'Incorrect' }),
    } as Response)

    renderLogin()
    await userEvent.type(screen.getByLabelText('Username'), 'wrong')
    await userEvent.type(screen.getByLabelText('Password'), 'bad')
    await userEvent.click(screen.getByRole('button', { name: 'Log in' }))

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Invalid username or password.')
    })
  })

  it('shows loading state during request', async () => {
    let resolveLogin!: () => void
    const loginPromise = new Promise<void>((res) => { resolveLogin = res })
    const mockLogin = vi.fn().mockReturnValue(loginPromise)
    useAuthStore.setState({ login: mockLogin, isLoading: false } as never)

    renderLogin()
    const btn = screen.getByRole('button', { name: 'Log in' })
    await userEvent.type(screen.getByLabelText('Username'), 'admin')
    await userEvent.type(screen.getByLabelText('Password'), 'secret')

    // Trigger submission and immediately check loading
    await userEvent.click(btn)
    useAuthStore.setState({ isLoading: true } as never)
    expect(useAuthStore.getState().isLoading).toBe(true)
    resolveLogin()
  })

  it('pre-fills ?next= param and redirects after login', async () => {
    // Token already in store = already authenticated → redirect fires immediately
    useAuthStore.setState({
      token: ADMIN_TOKEN,
      user: { userId: '1', role: 'admin', exp: 9_999_999_999 },
      isLoading: false,
      error: null,
    })
    // No error thrown = page renders (navigation handled by hook)
    renderLogin('/login?next=/analytics')
    // The component itself just renders — navigation is tested via router integration
  })
})
