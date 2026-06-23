import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { KpiCard } from './KpiCard'

describe('KpiCard', () => {
  it('renders label and value', () => {
    render(<KpiCard label="Head Count Peak" value={42} />)
    expect(screen.getByText('Head Count Peak')).toBeInTheDocument()
    expect(screen.getByText('42')).toBeInTheDocument()
  })

  it('renders unit when provided', () => {
    render(<KpiCard label="Avg Dwell" value={12.5} unit="min" />)
    expect(screen.getByText('min')).toBeInTheDocument()
  })

  it('shows loading skeleton when loading is true', () => {
    render(<KpiCard label="Uptime" value={null} loading />)
    expect(screen.getByRole('status', { name: 'Loading' })).toBeInTheDocument()
  })

  it('shows unavailable when error is true', () => {
    render(<KpiCard label="Uptime" value={null} error />)
    expect(screen.getByRole('alert')).toHaveTextContent('Unavailable')
  })

  it('shows em-dash when value is null and not loading or error', () => {
    render(<KpiCard label="Avg Dwell" value={null} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('has accessible container label', () => {
    render(<KpiCard label="Camera Uptime" value={98} unit="%" />)
    expect(screen.getByRole('generic', { name: 'Camera Uptime' })).toBeInTheDocument()
  })
})
