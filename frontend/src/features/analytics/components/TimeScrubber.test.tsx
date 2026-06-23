import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TimeScrubber } from './TimeScrubber'

describe('TimeScrubber', () => {
  it('renders Play button initially', () => {
    render(<TimeScrubber />)
    expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument()
  })

  it('toggles to Pause when Play is clicked', () => {
    render(<TimeScrubber />)
    fireEvent.click(screen.getByRole('button', { name: 'Play' }))
    expect(screen.getByRole('button', { name: 'Pause' })).toBeInTheDocument()
  })

  it('toggles back to Play when Pause is clicked', () => {
    render(<TimeScrubber />)
    fireEvent.click(screen.getByRole('button', { name: 'Play' }))
    fireEvent.click(screen.getByRole('button', { name: 'Pause' }))
    expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument()
  })

  it('marks 1× speed as pressed by default', () => {
    render(<TimeScrubber />)
    expect(screen.getByRole('button', { name: '1× speed' })).toHaveAttribute('aria-pressed', 'true')
  })

  it('switches speed when a speed button is clicked', () => {
    render(<TimeScrubber />)
    fireEvent.click(screen.getByRole('button', { name: '2× speed' }))
    expect(screen.getByRole('button', { name: '2× speed' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '1× speed' })).toHaveAttribute('aria-pressed', 'false')
  })

  it('shows deferred notice when disabled', () => {
    render(<TimeScrubber disabled />)
    expect(screen.getByRole('status')).toHaveTextContent('Timeline data pending')
  })

  it('disables Play button when disabled=true', () => {
    render(<TimeScrubber disabled />)
    expect(screen.getByRole('button', { name: 'Play' })).toBeDisabled()
  })

  it('pauses and steps position on Step forward', () => {
    render(<TimeScrubber />)
    fireEvent.click(screen.getByRole('button', { name: 'Play' }))
    fireEvent.click(screen.getByRole('button', { name: 'Step forward' }))
    expect(screen.getByRole('button', { name: 'Play' })).toBeInTheDocument()
  })

  it('renders scrubber position slider', () => {
    render(<TimeScrubber />)
    expect(screen.getByRole('slider', { name: 'Scrubber position' })).toBeInTheDocument()
  })
})
