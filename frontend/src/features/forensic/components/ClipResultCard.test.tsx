import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ClipResultCard } from './ClipResultCard'
import type { ForensicClip } from '@/shared/api/types'

const clip: ForensicClip = {
  global_track_id: 'track-001',
  camera_id: 3,
  zone_id: 2,
  score: 0.87,
  triggered_at: '2026-06-24T09:00:00Z',
  thumbnail_url: null,
  clip_url: null,
  duration_s: 10,
  alert_id: null,
}

describe('ClipResultCard', () => {
  it('renders camera metadata', () => {
    render(<ClipResultCard clip={clip} onClick={vi.fn()} />)
    expect(screen.getByText(/Camera 3/)).toBeInTheDocument()
  })

  it('renders zone metadata', () => {
    render(<ClipResultCard clip={clip} onClick={vi.fn()} />)
    expect(screen.getByText(/Zone 2/)).toBeInTheDocument()
  })

  it('shows score as percentage', () => {
    render(<ClipResultCard clip={clip} onClick={vi.fn()} />)
    expect(screen.getByText('Score 87%')).toBeInTheDocument()
  })

  it('shows duration when provided', () => {
    render(<ClipResultCard clip={clip} onClick={vi.fn()} />)
    expect(screen.getByText('10s')).toBeInTheDocument()
  })

  it('calls onClick when the card is clicked', () => {
    const onClick = vi.fn()
    render(<ClipResultCard clip={clip} onClick={onClick} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onClick).toHaveBeenCalledOnce()
  })

  it('shows no thumbnail img when thumbnail_url is null', () => {
    render(<ClipResultCard clip={clip} onClick={vi.fn()} />)
    expect(screen.queryByRole('img', { name: 'Clip thumbnail' })).toBeNull()
  })

  it('shows thumbnail image when thumbnail_url is provided', () => {
    render(<ClipResultCard clip={{ ...clip, thumbnail_url: '/thumb.jpg' }} onClick={vi.fn()} />)
    expect(screen.getByRole('img', { name: 'Clip thumbnail' })).toHaveAttribute(
      'src',
      '/thumb.jpg',
    )
  })

  it('does not show zone text when zone_id is null', () => {
    render(<ClipResultCard clip={{ ...clip, zone_id: null }} onClick={vi.fn()} />)
    expect(screen.queryByText(/Zone/)).toBeNull()
  })
})
