import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Switch, TOGGLE_SPRING } from './Switch'

describe('Switch §O micro-interactions', () => {
  it('spring type is spring', () => {
    expect(TOGGLE_SPRING.type).toBe('spring')
  })

  it('spring stiffness is 400', () => {
    expect(TOGGLE_SPRING.stiffness).toBe(400)
  })

  it('spring damping is 25', () => {
    expect(TOGGLE_SPRING.damping).toBe(25)
  })

  it('renders without error', () => {
    expect(() => render(<Switch />)).not.toThrow()
  })

  it('renders a switch role', () => {
    const { getByRole } = render(<Switch />)
    expect(getByRole('switch')).toBeInTheDocument()
  })
})
