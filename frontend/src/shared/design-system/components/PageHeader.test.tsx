import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { PageHeader } from './PageHeader'

describe('PageHeader', () => {
  it('renders title as h1', () => {
    render(<PageHeader title="System Dashboard" />)
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('System Dashboard')
  })

  it('renders optional subtitle when provided', () => {
    render(<PageHeader title="Cameras" subtitle="52 cameras configured" />)
    expect(screen.getByText('52 cameras configured')).toBeInTheDocument()
  })

  it('does not render subtitle element when omitted', () => {
    const { container } = render(<PageHeader title="Cameras" />)
    expect(container.querySelector('p')).not.toBeInTheDocument()
  })

  it('renders actions slot', () => {
    render(<PageHeader title="Persons" actions={<button>Enrol Person</button>} />)
    expect(screen.getByRole('button', { name: 'Enrol Person' })).toBeInTheDocument()
  })
})
