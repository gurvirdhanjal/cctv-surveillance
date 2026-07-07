import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { AdminLayout } from './AdminLayout'

const SRC = readFileSync(resolve(__dirname, './AdminLayout.tsx'), 'utf-8')

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

// §N premium navigation compliance checks
describe('AdminLayout §N nav compliance', () => {
  it('active indicator uses layoutId spring animation', () => {
    expect(SRC).toContain('layoutId="admin-nav-active"')
  })

  it('active indicator uses --brand-accent (only sanctioned brass moment)', () => {
    expect(SRC).toContain('var(--brand-accent)')
  })

  it('hover state does not use brass (bg-brand tokens forbidden on hover)', () => {
    // hover lines must not contain bg-brand
    const hoverMatches = SRC.match(/hover:[^\s"]+/g) ?? []
    const brassMisuse = hoverMatches.filter((cls) => cls.includes('brand'))
    expect(brassMisuse).toHaveLength(0)
  })

  it('active indicator background uses surface token not brass', () => {
    // The motion.span inside the active indicator must use bg-surface-*, not bg-brand
    const indicatorBlock = SRC.slice(
      SRC.indexOf('layoutId="admin-nav-active"'),
      SRC.indexOf('layoutId="admin-nav-active"') + 200,
    )
    expect(indicatorBlock).not.toMatch(/bg-brand/)
    expect(indicatorBlock).toMatch(/bg-surface/)
  })

  it('logo uses --brand-accent (sanctioned location)', () => {
    expect(SRC).toContain('function VmsLogo')
    const logoFn = SRC.slice(
      SRC.indexOf('function VmsLogo'),
      SRC.indexOf('function VmsLogo') + 600,
    )
    expect(logoFn).toContain('brand-accent')
  })

  it('renders without brass on nav links in DOM', () => {
    const { container } = render(
      <HelmetProvider>
        <MemoryRouter initialEntries={['/admin']}>
          <AdminLayout />
        </MemoryRouter>
      </HelmetProvider>,
    )
    const navLinks = Array.from(container.querySelectorAll('nav a'))
    navLinks.forEach((link) => {
      expect(link.className).not.toMatch(/bg-brand/)
    })
  })
})
