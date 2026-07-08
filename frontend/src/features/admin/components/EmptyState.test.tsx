import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Icon } from '@/shared/design-system/icons'
import { EmptyState } from './EmptyState'

describe('EmptyState (admin re-export)', () => {
  it('renders icon, title, description and cta', () => {
    render(
      <EmptyState
        icon={Icon.users}
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
      <EmptyState icon={Icon.users} title="Nothing here" cta={<span>placeholder</span>} />,
    )
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
  })

  it('renders the cta slot', () => {
    render(
      <EmptyState
        icon={Icon.users}
        title="No items"
        cta={<button type="button">Add item</button>}
      />,
    )
    expect(screen.getByRole('button', { name: 'Add item' })).toBeInTheDocument()
  })
})
