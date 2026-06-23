import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CameraTile } from './CameraTile'
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

  it('applies brand border when focused', () => {
    const { container } = render(
      <CameraTile camera={makeCamera()} isFocused={true} onSelect={vi.fn()} />,
    )
    const btn = container.querySelector('button')
    expect(btn?.className).toMatch(/border-brand-500/)
  })

  it('applies amber border for auth_failed status when not focused', () => {
    const { container } = render(
      <CameraTile camera={makeCamera({ status: 'auth_failed' })} isFocused={false} onSelect={vi.fn()} />,
    )
    const btn = container.querySelector('button')
    expect(btn?.className).toMatch(/border-status-auth-failed/)
  })

  it('shows calendar icon for maintenance status', () => {
    render(
      <CameraTile camera={makeCamera({ status: 'maintenance' })} isFocused={false} onSelect={vi.fn()} />,
    )
    expect(screen.getByLabelText('Under maintenance')).toBeInTheDocument()
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
})
