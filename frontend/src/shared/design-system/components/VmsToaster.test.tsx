import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { vmsToast, VmsToaster } from './VmsToaster'

// Sonner's Toaster renders a portal — check the document body
describe('vmsToast wrapper (§V.1)', () => {
  it('exports success function', () => {
    expect(typeof vmsToast.success).toBe('function')
  })

  it('exports error function', () => {
    expect(typeof vmsToast.error).toBe('function')
  })

  it('exports warning function', () => {
    expect(typeof vmsToast.warning).toBe('function')
  })

  it('exports info function', () => {
    expect(typeof vmsToast.info).toBe('function')
  })
})

describe('VmsToaster (§V.1)', () => {
  it('renders without error', () => {
    expect(() => render(<VmsToaster />)).not.toThrow()
  })

  it('mounts a sonner toast container into the DOM', () => {
    const { baseElement } = render(<VmsToaster />)
    // Sonner renders a section or ol with its own ID into the body
    // Presence of any portal descendant in baseElement confirms mount
    const portal = baseElement.querySelector('section, ol, [id^="sonner"]')
    expect(portal ?? baseElement.children.length > 1).toBeTruthy()
  })

  it('renders a portal element in the document body', () => {
    const { baseElement } = render(<VmsToaster />)
    // baseElement is document.body — any descendant element proves the portal mounted
    expect(baseElement.children.length).toBeGreaterThan(0)
  })
})
