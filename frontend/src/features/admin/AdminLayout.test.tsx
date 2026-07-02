import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { AdminLayout } from './AdminLayout'

function renderLayout() {
  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={['/admin']}>
        <AdminLayout />
      </MemoryRouter>
    </HelmetProvider>,
  )
}

describe('AdminLayout', () => {
  it('renders admin navigation landmark', () => {
    renderLayout()
    expect(screen.getByRole('navigation', { name: 'Admin navigation' })).toBeInTheDocument()
  })

  it('renders all nav links', () => {
    renderLayout()
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Persons' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Cameras' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Zones' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Users' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Maintenance' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Anomaly Detectors' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Alert Routing' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Models' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Audit Log' })).toBeInTheDocument()
  })

  it('renders main content area', () => {
    renderLayout()
    expect(screen.getByRole('main')).toBeInTheDocument()
  })

  it('Dashboard link points to /admin', () => {
    renderLayout()
    const link = screen.getByRole('link', { name: 'Dashboard' })
    expect(link).toHaveAttribute('href', '/admin')
  })
})
