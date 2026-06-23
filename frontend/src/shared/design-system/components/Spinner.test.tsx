import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Spinner } from './Spinner'

describe('Spinner', () => {
  it('renders with default size', () => {
    const { container } = render(<Spinner />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('width', '16')
  })

  it('renders with custom size', () => {
    const { container } = render(<Spinner size={24} />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('width', '24')
  })

  it('has status role when not aria-hidden', () => {
    const { getByRole } = render(<Spinner />)
    expect(getByRole('status')).toBeInTheDocument()
  })

  it('has no role when aria-hidden', () => {
    const { container } = render(<Spinner aria-hidden />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('aria-hidden', 'true')
  })
})
