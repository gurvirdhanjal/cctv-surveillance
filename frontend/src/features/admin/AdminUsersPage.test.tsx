import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'

const { AdminUsersPage } = await import('./AdminUsersPage')

describe('AdminUsersPage', () => {
  it('renders page heading', () => {
    render(
      <HelmetProvider>
        <MemoryRouter>
          <AdminUsersPage />
        </MemoryRouter>
      </HelmetProvider>,
    )
    expect(screen.getByRole('heading', { name: 'Users' })).toBeInTheDocument()
  })

  it('shows API unavailable notice', () => {
    render(
      <HelmetProvider>
        <MemoryRouter>
          <AdminUsersPage />
        </MemoryRouter>
      </HelmetProvider>,
    )
    expect(
      screen.getByRole('status', { name: 'Users API unavailable' }),
    ).toBeInTheDocument()
  })

  it('references the P3 pre-work sub-task tracking', () => {
    render(
      <HelmetProvider>
        <MemoryRouter>
          <AdminUsersPage />
        </MemoryRouter>
      </HelmetProvider>,
    )
    expect(screen.getByText(/pre-work P3/)).toBeInTheDocument()
  })
})
