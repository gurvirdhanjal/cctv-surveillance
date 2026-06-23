import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Badge } from './Badge'

describe('Badge', () => {
  it('renders children', () => {
    render(<Badge>CRITICAL</Badge>)
    expect(screen.getByText('CRITICAL')).toBeInTheDocument()
  })

  it('renders critical variant', () => {
    render(<Badge variant="critical">CRITICAL</Badge>)
    const badge = screen.getByText('CRITICAL')
    expect(badge).toBeInTheDocument()
  })

  it('renders severity variants without throwing', () => {
    const { rerender } = render(<Badge variant="critical">CRITICAL</Badge>)
    rerender(<Badge variant="high">HIGH</Badge>)
    rerender(<Badge variant="medium">MEDIUM</Badge>)
    rerender(<Badge variant="low">LOW</Badge>)
    expect(screen.getByText('LOW')).toBeInTheDocument()
  })

  it('renders tier variants', () => {
    render(<Badge variant="full">FULL</Badge>)
    expect(screen.getByText('FULL')).toBeInTheDocument()
  })
})
