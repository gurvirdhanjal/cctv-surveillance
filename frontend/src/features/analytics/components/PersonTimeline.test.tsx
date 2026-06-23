import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PersonTimeline } from './PersonTimeline'

const presences = [
  { zone_name: 'Entrance', start_hour: 8, end_hour: 9 },
  { zone_name: 'Assembly', start_hour: 9, end_hour: 17 },
  { zone_name: 'Entrance', start_hour: 17, end_hour: 18 },
]

describe('PersonTimeline', () => {
  it('renders timeline container with accessible label', () => {
    render(<PersonTimeline presences={presences} />)
    expect(screen.getByLabelText('Person zone timeline')).toBeInTheDocument()
  })

  it('renders a row for each unique zone', () => {
    render(<PersonTimeline presences={presences} />)
    expect(document.querySelector('[data-zone="Entrance"]')).toBeInTheDocument()
    expect(document.querySelector('[data-zone="Assembly"]')).toBeInTheDocument()
  })

  it('renders presence blocks with aria-labels for each interval', () => {
    render(<PersonTimeline presences={presences} />)
    expect(screen.getByLabelText('Entrance 8h–9h')).toBeInTheDocument()
    expect(screen.getByLabelText('Assembly 9h–17h')).toBeInTheDocument()
    expect(screen.getByLabelText('Entrance 17h–18h')).toBeInTheDocument()
  })

  it('renders empty state without errors when no presences', () => {
    render(<PersonTimeline presences={[]} />)
    expect(screen.getByLabelText('Person zone timeline')).toBeInTheDocument()
  })

  it('renders legend entries for each zone', () => {
    render(<PersonTimeline presences={presences} />)
    const entranceLabels = screen.getAllByText('Entrance')
    expect(entranceLabels.length).toBeGreaterThanOrEqual(1)
    const assemblyLabels = screen.getAllByText('Assembly')
    expect(assemblyLabels.length).toBeGreaterThanOrEqual(1)
  })
})
