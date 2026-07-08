import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CameraTile, CAMERA_TILE_HOVER_SCALE } from './CameraTile'
import { useLiveStore } from '../store/liveStore'
import type { CameraState } from '../types'

vi.mock('../hooks/useCameraSnapshot', () => ({
  useCameraSnapshot: vi.fn(() => '/api/cameras/1/snapshot?t=0'),
}))

const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
})

function makeCamera(overrides: Partial<CameraState> = {}): CameraState {
  return {
    camera_id: 1,
    name: 'Loading Bay',
    capability_tier: 'FULL',
    status: 'online',
    is_active: true,
    snapshotUrl: null,
    ...overrides,
  }
}

describe('CameraTile', () => {
  it('renders camera name', () => {
    render(<CameraTile camera={makeCamera()} isFocused={false} onSelect={vi.fn()} />)
    expect(screen.getByText('Loading Bay')).toBeInTheDocument()
  })

  it('renders tier badge', () => {
    render(<CameraTile camera={makeCamera({ capability_tier: 'MID' })} isFocused={false} onSelect={vi.fn()} />)
    expect(screen.getByText('MID')).toBeInTheDocument()
  })

  it('applies ring-white/40 when focused (dark console style)', () => {
    const { container } = render(
      <CameraTile camera={makeCamera()} isFocused={true} onSelect={vi.fn()} />,
    )
    const btn = container.querySelector('button')
    expect(btn?.className).toContain('ring-white/40')
  })

  it('does not apply ring-white/40 when not focused', () => {
    const { container } = render(
      <CameraTile camera={makeCamera()} isFocused={false} onSelect={vi.fn()} />,
    )
    const btn = container.querySelector('button')
    expect(btn?.className).not.toContain('ring-white/40')
  })

  it('applies alarming border when isAlarming=true', () => {
    const { container } = render(
      <CameraTile camera={makeCamera()} isFocused={false} isAlarming onSelect={vi.fn()} />,
    )
    const btn = container.querySelector('button')
    expect(btn?.className).toContain('border-[#dc2626]')
  })

  it('applies reduced opacity for maintenance status', () => {
    const { container } = render(
      <CameraTile camera={makeCamera({ status: 'maintenance' })} isFocused={false} onSelect={vi.fn()} />,
    )
    const btn = container.querySelector('button')
    expect(btn?.className).toContain('opacity-60')
  })

  it('calls onSelect when clicked', () => {
    const onSelect = vi.fn()
    render(<CameraTile camera={makeCamera()} isFocused={false} onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button'))
    expect(onSelect).toHaveBeenCalledOnce()
  })

  it('has aria-pressed=true when focused', () => {
    render(<CameraTile camera={makeCamera()} isFocused={true} onSelect={vi.fn()} />)
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true')
  })

  it('has accessible label including camera name', () => {
    render(<CameraTile camera={makeCamera()} isFocused={false} onSelect={vi.fn()} />)
    expect(screen.getByLabelText('Focus camera Loading Bay')).toBeInTheDocument()
  })

  it('exports CAMERA_TILE_HOVER_SCALE === 1.02', () => {
    expect(CAMERA_TILE_HOVER_SCALE).toBe(1.02)
  })

  it('shows REC badge when recording=true', () => {
    render(<CameraTile camera={makeCamera()} isFocused={false} onSelect={vi.fn()} recording={true} />)
    expect(screen.getByLabelText('Recording')).toBeInTheDocument()
  })

  it('does not show REC badge when recording=false', () => {
    render(<CameraTile camera={makeCamera()} isFocused={false} onSelect={vi.fn()} />)
    expect(screen.queryByLabelText('Recording')).not.toBeInTheDocument()
  })

  it('PTZ button is disabled for non-FULL tier', () => {
    render(
      <CameraTile
        camera={makeCamera({ capability_tier: 'MID' })}
        isFocused={false}
        onSelect={vi.fn()}
      />,
    )
    const tileEl = screen.getByLabelText('Focus camera Loading Bay').closest('div')!
    fireEvent.mouseEnter(tileEl)
    const ptzBtn = screen.getByRole('button', { name: 'PTZ' })
    expect(ptzBtn).toBeDisabled()
  })

  it('PTZ button is enabled for FULL tier', () => {
    render(
      <CameraTile
        camera={makeCamera({ capability_tier: 'FULL' })}
        isFocused={false}
        onSelect={vi.fn()}
      />,
    )
    const tileEl = screen.getByLabelText('Focus camera Loading Bay').closest('div')!
    fireEvent.mouseEnter(tileEl)
    const ptzBtn = screen.getByRole('button', { name: 'PTZ' })
    expect(ptzBtn).not.toBeDisabled()
  })
})
