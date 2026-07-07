import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PersonDot } from './PersonDot'
import type { PersonLocation } from '../types'

function makeLoc(overrides: Partial<PersonLocation> = {}): PersonLocation {
  return {
    global_track_id: 'gid-1',
    person_id: null,
    camera_id: 1,
    bbox: [0, 0, 0.5, 0.5],
    floor_x: 0.3,
    floor_y: 0.6,
    ts: '2026-06-24T10:00:00Z',
    ...overrides,
  }
}

describe('PersonDot', () => {
  it('renders at the correct floor position', () => {
    const { container } = render(<PersonDot location={makeLoc({ floor_x: 0.3, floor_y: 0.6 })} />)
    const dot = container.querySelector('[data-track-id]')
    expect(dot).toHaveStyle({ left: '30%', top: '60%' })
  })

  it('labels unknown person correctly', () => {
    render(<PersonDot location={makeLoc({ person_id: null })} />)
    expect(screen.getByLabelText('Unknown person')).toBeInTheDocument()
  })

  it('labels known person with ID', () => {
    render(<PersonDot location={makeLoc({ person_id: 42 })} />)
    expect(screen.getByLabelText('Person #42')).toBeInTheDocument()
  })

  it('uses action colour for known person', () => {
    const { container } = render(<PersonDot location={makeLoc({ person_id: 5 })} />)
    const dot = container.querySelector('[data-track-id]')
    expect(dot?.className).toMatch(/bg-action-700/)
  })

  it('uses critical colour for unknown person', () => {
    const { container } = render(<PersonDot location={makeLoc({ person_id: null })} />)
    const dot = container.querySelector('[data-track-id]')
    expect(dot?.className).toMatch(/bg-severity-critical/)
  })
})
