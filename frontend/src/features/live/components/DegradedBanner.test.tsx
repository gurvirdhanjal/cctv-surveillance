import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useLiveStore } from '../store/liveStore'
import { DegradedBanner } from './DegradedBanner'

describe('DegradedBanner', () => {
  beforeEach(() => {
    useLiveStore.setState({ degraded: null })
  })

  it('renders nothing when not degraded', () => {
    const { container } = render(<DegradedBanner />)
    expect(container.firstChild).toBeNull()
  })

  it('renders reconnecting banner when degraded', () => {
    useLiveStore.setState({ degraded: { connection: 'lost' } })
    render(<DegradedBanner />)
    expect(screen.getByRole('status', { name: 'Connection degraded' })).toBeInTheDocument()
    expect(screen.getByText(/Reconnecting/)).toBeInTheDocument()
  })

  it('has aria-live polite for screen readers', () => {
    useLiveStore.setState({ degraded: { connection: 'lost' } })
    render(<DegradedBanner />)
    expect(screen.getByRole('status')).toHaveAttribute('aria-live', 'polite')
  })
})
