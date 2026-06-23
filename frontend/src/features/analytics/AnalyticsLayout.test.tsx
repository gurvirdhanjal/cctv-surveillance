import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'
import { AnalyticsLayout } from './AnalyticsLayout'

function renderLayout(path = '/analytics') {
  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={[path]}>
        <AnalyticsLayout />
      </MemoryRouter>
    </HelmetProvider>,
  )
}

describe('AnalyticsLayout', () => {
  it('renders analytics navigation', () => {
    renderLayout()
    expect(screen.getByRole('navigation', { name: 'Analytics navigation' })).toBeInTheDocument()
  })

  it('renders Dashboard nav link', () => {
    renderLayout()
    expect(screen.getByRole('link', { name: 'Dashboard' })).toBeInTheDocument()
  })

  it('renders Timeline nav link', () => {
    renderLayout()
    expect(screen.getByRole('link', { name: 'Timeline' })).toBeInTheDocument()
  })

  it('renders Heatmap nav link', () => {
    renderLayout()
    expect(screen.getByRole('link', { name: 'Heatmap' })).toBeInTheDocument()
  })

  it('renders Forensic Search link', () => {
    renderLayout()
    expect(screen.getByRole('link', { name: 'Forensic Search' })).toBeInTheDocument()
  })

  it('renders main content area', () => {
    renderLayout()
    expect(screen.getByRole('main')).toBeInTheDocument()
  })
})
