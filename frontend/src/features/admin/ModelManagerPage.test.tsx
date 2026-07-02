import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { HelmetProvider } from 'react-helmet-async'

const { ModelManagerPage } = await import('./ModelManagerPage')

function renderPage() {
  return render(
    <HelmetProvider>
      <MemoryRouter>
        <ModelManagerPage />
      </MemoryRouter>
    </HelmetProvider>,
  )
}

describe('ModelManagerPage', () => {
  it('renders page heading', () => {
    renderPage()
    expect(screen.getByRole('heading', { name: 'Models' })).toBeInTheDocument()
  })

  it('shows Models API unavailable notice', () => {
    renderPage()
    expect(screen.getByRole('status', { name: 'Models API unavailable' })).toBeInTheDocument()
  })

  it('references vms-models CLI', () => {
    renderPage()
    expect(screen.getByText('vms-models')).toBeInTheDocument()
  })

  it('references the P4 pre-work sub-task', () => {
    renderPage()
    expect(screen.getByText(/pre-work P4/)).toBeInTheDocument()
  })
})
