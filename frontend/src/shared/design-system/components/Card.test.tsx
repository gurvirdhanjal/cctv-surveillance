import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Card } from './Card'

describe('Card (§A)', () => {
  it('renders Card.Root as a div by default', () => {
    const { container } = render(<Card.Root variant="metric">content</Card.Root>)
    expect(container.firstElementChild?.tagName).toBe('DIV')
  })

  it('renders all 6 spec variants without error', () => {
    const variants = ['metric', 'health', 'camera', 'alarm', 'timeline', 'configuration'] as const
    for (const variant of variants) {
      expect(() => render(<Card.Root variant={variant}>x</Card.Root>)).not.toThrow()
    }
  })

  it('applies rounded-xl by default', () => {
    const { container } = render(<Card.Root variant="metric">x</Card.Root>)
    expect((container.firstElementChild as HTMLElement).className).toContain('rounded-xl')
  })

  it('renders Card.Header, Card.Body, Card.Footer subcomponents', () => {
    const { getByText } = render(
      <Card.Root variant="configuration">
        <Card.Header>Header text</Card.Header>
        <Card.Body>Body text</Card.Body>
        <Card.Footer>Footer text</Card.Footer>
      </Card.Root>,
    )
    expect(getByText('Header text')).toBeTruthy()
    expect(getByText('Body text')).toBeTruthy()
    expect(getByText('Footer text')).toBeTruthy()
  })

  it('renders Card.Actions subcomponent', () => {
    const { getByText } = render(
      <Card.Root variant="alarm">
        <Card.Actions><button>Action</button></Card.Actions>
      </Card.Root>,
    )
    expect(getByText('Action')).toBeTruthy()
  })

  it('forwards className on Card.Root', () => {
    const { container } = render(<Card.Root variant="health" className="custom">x</Card.Root>)
    expect((container.firstElementChild as HTMLElement).className).toContain('custom')
  })
})
