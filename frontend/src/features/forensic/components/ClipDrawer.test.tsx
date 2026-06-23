import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import type { ForensicClip } from '@/shared/api/types'

const { MockHls: ClipDrawerHls } = vi.hoisted(() => {
  const MockHls = vi.fn(() => ({
    loadSource: vi.fn(),
    attachMedia: vi.fn(),
    destroy: vi.fn(),
  }))
  Object.assign(MockHls, { isSupported: vi.fn(() => false) })
  return { MockHls }
})

vi.mock('hls.js', () => ({ default: ClipDrawerHls }))

const { ClipDrawer } = await import('./ClipDrawer')

const clip: ForensicClip = {
  global_track_id: 'track-abc',
  camera_id: 5,
  zone_id: 1,
  score: 0.92,
  triggered_at: '2026-06-24T08:30:00Z',
  thumbnail_url: null,
  clip_url: null,
  duration_s: 10,
  alert_id: null,
}

function renderDrawer(c = clip, onClose = vi.fn()) {
  return render(
    <MemoryRouter>
      <ClipDrawer clip={c} onClose={onClose} />
    </MemoryRouter>,
  )
}

describe('ClipDrawer', () => {
  it('renders drawer title with camera id', () => {
    renderDrawer()
    expect(screen.getByText(/Camera 5/)).toBeInTheDocument()
  })

  it('renders track id', () => {
    renderDrawer()
    expect(screen.getByText('track-abc')).toBeInTheDocument()
  })

  it('shows score formatted as percentage', () => {
    renderDrawer()
    expect(screen.getByText('92.0%')).toBeInTheDocument()
  })

  it('shows "Video clip unavailable" when clip_url is null', () => {
    renderDrawer()
    expect(screen.getByText('Video clip unavailable')).toBeInTheDocument()
  })

  it('calls onClose when close button is clicked', () => {
    const onClose = vi.fn()
    renderDrawer(clip, onClose)
    fireEvent.click(screen.getByRole('button', { name: 'Close drawer' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('renders "open in timeline scrubber" link', () => {
    renderDrawer()
    expect(screen.getByRole('link', { name: 'Open in timeline scrubber' })).toBeInTheDocument()
  })

  it('renders zone metadata when zone_id is provided', () => {
    renderDrawer()
    expect(screen.getByText('Zone')).toBeInTheDocument()
  })
})
