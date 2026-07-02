import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import axe from 'axe-core'
import { Button } from './Button'
import { Input } from './Input'
import { Modal } from './Modal'
import { Badge } from './Badge'
import { ToastProvider } from './Toast'

describe('Button a11y', () => {
  it('all variants have no violations', async () => {
    const { container } = render(
      <div>
        <Button>Primary</Button>
        <Button variant="secondary">Secondary</Button>
        <Button variant="ghost">Ghost</Button>
        <Button variant="destructive">Delete</Button>
        <Button disabled>Disabled</Button>
        <Button loading>Saving</Button>
      </div>,
    )
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })
})

describe('Input a11y', () => {
  it('input with label has no violations', async () => {
    const { container } = render(<Input label="Username" />)
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })

  it('input with error has no violations', async () => {
    const { container } = render(<Input label="Email" error="Invalid email address" />)
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })

  it('input with hint has no violations', async () => {
    const { container } = render(<Input label="Employee ID" hint="Format: EMP-XXXX" />)
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })

  it('hidden-label input has no violations', async () => {
    const { container } = render(<Input label="Search" labelHidden placeholder="Search…" />)
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })

  it('password input has no violations', async () => {
    const { container } = render(<Input label="Password" type="password" autoComplete="current-password" />)
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })
})

describe('Modal a11y', () => {
  it('open modal has no violations', async () => {
    render(<Modal open onClose={vi.fn()} title="Confirm action">Are you sure?</Modal>)
    const results = await axe.run(document.body)
    expect(results.violations).toHaveLength(0)
  })

  it('open modal with description has no violations', async () => {
    render(
      <Modal
        open
        onClose={vi.fn()}
        title="Delete zone"
        description="This action cannot be undone."
      >
        <p>Zone details here</p>
      </Modal>,
    )
    const results = await axe.run(document.body)
    expect(results.violations).toHaveLength(0)
  })
})

describe('Badge a11y', () => {
  it('all severity variants have no violations', async () => {
    const { container } = render(
      <div>
        <Badge variant="critical">Critical</Badge>
        <Badge variant="high">High</Badge>
        <Badge variant="medium">Medium</Badge>
        <Badge variant="low">Low</Badge>
        <Badge variant="success">Active</Badge>
        <Badge variant="default">Offline</Badge>
        <Badge variant="info">Info</Badge>
        <Badge variant="warning">Warning</Badge>
      </div>,
    )
    const results = await axe.run(container)
    expect(results.violations).toHaveLength(0)
  })
})

describe('Toast a11y', () => {
  it('success toast has no violations', async () => {
    render(
      <ToastProvider
        toasts={[{ id: '1', severity: 'success', title: 'Saved', description: 'Changes persisted.' }]}
        onDismiss={vi.fn()}
      />,
    )
    const results = await axe.run(document.body)
    expect(results.violations).toHaveLength(0)
  })

  it('error toast has no violations', async () => {
    render(
      <ToastProvider
        toasts={[{ id: '1', severity: 'error', title: 'Error', description: 'Request failed.' }]}
        onDismiss={vi.fn()}
      />,
    )
    const results = await axe.run(document.body)
    expect(results.violations).toHaveLength(0)
  })
})
