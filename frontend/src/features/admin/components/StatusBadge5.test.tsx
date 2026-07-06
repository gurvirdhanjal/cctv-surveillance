import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { StatusBadge5 } from './StatusBadge5'

describe('StatusBadge5', () => {
  it('renders Online state', () => {
    render(<StatusBadge5 state="online" />)
    expect(screen.getByText('Online')).toBeInTheDocument()
  })

  it('renders Offline state', () => {
    render(<StatusBadge5 state="offline" />)
    expect(screen.getByText('Offline')).toBeInTheDocument()
  })

  it('renders Maintenance state', () => {
    render(<StatusBadge5 state="maintenance" />)
    expect(screen.getByText('Maintenance')).toBeInTheDocument()
  })

  it('renders Auth Failed state', () => {
    render(<StatusBadge5 state="auth_failed" />)
    expect(screen.getByText('Auth Failed')).toBeInTheDocument()
  })

  it('renders Critical state', () => {
    render(<StatusBadge5 state="critical" />)
    expect(screen.getByText('Critical')).toBeInTheDocument()
  })
})
