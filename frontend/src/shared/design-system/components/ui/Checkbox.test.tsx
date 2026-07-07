import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Checkbox, CHECKBOX_SPRING } from './Checkbox'

describe('Checkbox §O micro-interactions', () => {
  it('spring type is spring', () => {
    expect(CHECKBOX_SPRING.type).toBe('spring')
  })

  it('spring stiffness is 500', () => {
    expect(CHECKBOX_SPRING.stiffness).toBe(500)
  })

  it('spring damping is 30', () => {
    expect(CHECKBOX_SPRING.damping).toBe(30)
  })

  it('renders without error', () => {
    expect(() => render(<Checkbox />)).not.toThrow()
  })

  it('renders a checkbox role', () => {
    const { getByRole } = render(<Checkbox />)
    expect(getByRole('checkbox')).toBeInTheDocument()
  })
})
