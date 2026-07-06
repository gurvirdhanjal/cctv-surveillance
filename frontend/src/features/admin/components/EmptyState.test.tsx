import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Users } from 'lucide-react'
import { EmptyState } from './EmptyState'

describe('EmptyState', () => {
  it('renders icon, title, and description', () => {
    render(
      <EmptyState
        icon={Users}
        title="No persons enrolled"
        description="Use the enrolment wizard to add the first person."
      />,
    )
    expect(screen.getByText('No persons enrolled')).toBeInTheDocument()
    expect(screen.getByText('Use the enrolment wizard to add the first person.')).toBeInTheDocument()
  })

  it('renders without description', () => {
    render(<EmptyState icon={Users} title="Nothing here" />)
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
  })

  it('renders optional action', () => {
    render(
      <EmptyState
        icon={Users}
        title="No items"
        action={<button type="button">Add item</button>}
      />,
    )
    expect(screen.getByRole('button', { name: 'Add item' })).toBeInTheDocument()
  })
})
