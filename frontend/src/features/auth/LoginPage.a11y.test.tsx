import { describe, it, expect, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import axe from 'axe-core'
import { LoginPage } from './LoginPage'
import { useAuthStore } from '@/stores/authStore'

const initialAuthState = useAuthStore.getState()

beforeEach(() => {
  localStorage.clear()
  useAuthStore.setState(initialAuthState, true)
})

function renderLogin() {
  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={['/login']}>
        <LoginPage />
      </MemoryRouter>
    </HelmetProvider>,
  )
}

describe('LoginPage a11y', () => {
  it('login form has no violations', async () => {
    const { container } = renderLogin()
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })

  it('form with validation errors has no violations', async () => {
    const { container } = renderLogin()
    // Submit empty to trigger validation errors
    await userEvent.click(container.querySelector('button[type="submit"]')!)
    await waitFor(() => {
      expect(container.querySelector('[role="alert"]')).toBeInTheDocument()
    })
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })
})
