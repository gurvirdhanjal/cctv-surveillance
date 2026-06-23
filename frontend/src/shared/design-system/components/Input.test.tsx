import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Input } from './Input'

describe('Input', () => {
  it('renders a labeled input', () => {
    render(<Input label="Zone name" />)
    expect(screen.getByLabelText('Zone name')).toBeInTheDocument()
  })

  it('label is associated with input via htmlFor/id', () => {
    render(<Input label="Employee ID" />)
    const input = screen.getByLabelText('Employee ID')
    expect(input.tagName).toBe('INPUT')
  })

  it('shows error message with role=alert', () => {
    render(<Input label="Name" error="Name is required" />)
    const error = screen.getByRole('alert')
    expect(error).toHaveTextContent('Name is required')
  })

  it('sets aria-invalid when error is provided', () => {
    render(<Input label="Name" error="Required" />)
    expect(screen.getByLabelText('Name')).toHaveAttribute('aria-invalid', 'true')
  })

  it('links error via aria-describedby', () => {
    render(<Input label="Name" error="Required" />)
    const input = screen.getByLabelText('Name')
    const describedBy = input.getAttribute('aria-describedby')
    expect(describedBy).toBeTruthy()
    const errorEl = document.getElementById(describedBy!)
    expect(errorEl).toHaveTextContent('Required')
  })

  it('does not set aria-invalid when no error', () => {
    render(<Input label="Name" />)
    expect(screen.getByLabelText('Name')).not.toHaveAttribute('aria-invalid')
  })

  it('renders hint text when provided', () => {
    render(<Input label="Password" hint="At least 8 characters" />)
    expect(screen.getByText('At least 8 characters')).toBeInTheDocument()
  })

  it('hides label visually with labelHidden but keeps it accessible', () => {
    render(<Input label="Search" labelHidden />)
    const label = screen.getByText('Search')
    expect(label).toHaveClass('sr-only')
    expect(screen.getByLabelText('Search')).toBeInTheDocument()
  })
})
