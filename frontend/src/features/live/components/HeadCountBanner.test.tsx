import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { HeadCountBanner } from './HeadCountBanner'
import { useLiveStore } from '../store/liveStore'

const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
})

describe('HeadCountBanner', () => {
  it('renders total head count', () => {
    useLiveStore.setState({ headCount: { total: 17, byZone: {} } })
    render(<HeadCountBanner />)
    expect(screen.getByText('17')).toBeInTheDocument()
  })

  it('does not show zone breakdown by default', () => {
    render(<HeadCountBanner />)
    expect(screen.queryByRole('region', { name: 'Per-zone head count' })).toBeNull()
  })

  it('expands to show per-zone breakdown on click', () => {
    useLiveStore.setState({ headCount: { total: 5, byZone: { 1: 3, 2: 2 } } })
    render(<HeadCountBanner />)
    fireEvent.click(screen.getByLabelText('Head count breakdown'))
    expect(screen.getByRole('region', { name: 'Per-zone head count' })).toBeInTheDocument()
    expect(screen.getByText('Zone 1')).toBeInTheDocument()
    expect(screen.getByText('Zone 2')).toBeInTheDocument()
  })

  it('shows "stale" indicator in degraded mode', () => {
    useLiveStore.setState({ degraded: { connection: 'lost' } })
    render(<HeadCountBanner />)
    expect(screen.getByRole('status')).toHaveTextContent('stale')
  })

  it('does not show stale indicator in normal mode', () => {
    useLiveStore.setState({ degraded: null })
    render(<HeadCountBanner />)
    expect(screen.queryByRole('status')).toBeNull()
  })

  it('collapses when clicked a second time', () => {
    render(<HeadCountBanner />)
    const btn = screen.getByLabelText('Head count breakdown')
    fireEvent.click(btn)
    expect(btn).toHaveAttribute('aria-expanded', 'true')
    fireEvent.click(btn)
    expect(btn).toHaveAttribute('aria-expanded', 'false')
  })
})
