import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Users } from 'lucide-react'
import { EmptyState } from './EmptyState'

describe('EmptyState (§T rule 5)', () => {
  it('renders icon, title, description and cta', () => {
    render(
      <EmptyState
        icon={Users}
        title="No persons enrolled"
        description="Use the enrolment wizard to add the first person."
        cta={<button type="button">Enrol Person</button>}
      />,
    )
    expect(screen.getByText('No persons enrolled')).toBeInTheDocument()
    expect(screen.getByText('Use the enrolment wizard to add the first person.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Enrol Person' })).toBeInTheDocument()
  })

  it('renders without description', () => {
    render(
      <EmptyState
        icon={Users}
        title="Nothing here"
        cta={<button type="button">Add</button>}
      />,
    )
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
  })

  it('always renders the cta slot', () => {
    render(
      <EmptyState
        icon={Users}
        title="No items"
        cta={<button type="button">Add item</button>}
      />,
    )
    expect(screen.getByRole('button', { name: 'Add item' })).toBeInTheDocument()
  })

  it('accepts className override', () => {
    const { container } = render(
      <EmptyState icon={Users} title="T" cta={<span>CTA</span>} className="custom-cls" />
    )
    expect(container.firstChild).toHaveClass('custom-cls')
  })
})
