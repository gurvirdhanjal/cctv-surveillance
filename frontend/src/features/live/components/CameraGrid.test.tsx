import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { CameraGrid } from './CameraGrid'
import type { CameraState } from '../types'

vi.mock('./CameraTile', () => ({
  CameraTile: vi.fn(({ camera, isFocused, onSelect }: {
    camera: CameraState; isFocused: boolean; onSelect: () => void
  }) => (
    <button
      data-testid={`tile-${camera.camera_id}`}
      aria-pressed={isFocused}
      onClick={onSelect}
    >
      {camera.name}
    </button>
  )),
}))

function makeCamera(id: number): CameraState {
  return {
    camera_id: id,
    name: `Camera ${id}`,
    capability_tier: 'FULL',
    status: 'online',
    is_active: true,
    snapshotUrl: null,
  }
}

const cameras = Array.from({ length: 15 }, (_, i) => makeCamera(i + 1))

beforeEach(() => {
  vi.clearAllMocks()
})

describe('CameraGrid', () => {
  it('renders first 12 cameras on page 0', () => {
    render(<CameraGrid cameras={cameras} focusedCameraId={null} onCameraSelect={vi.fn()} />)
    expect(screen.getByTestId('tile-1')).toBeInTheDocument()
    expect(screen.getByTestId('tile-12')).toBeInTheDocument()
    expect(screen.queryByTestId('tile-13')).toBeNull()
  })

  it('shows pagination controls when more than 12 cameras', () => {
    render(<CameraGrid cameras={cameras} focusedCameraId={null} onCameraSelect={vi.fn()} />)
    expect(screen.getByLabelText('Next page')).toBeInTheDocument()
  })

  it('navigates to next page on next-page button click', () => {
    render(<CameraGrid cameras={cameras} focusedCameraId={null} onCameraSelect={vi.fn()} />)
    fireEvent.click(screen.getByLabelText('Next page'))
    expect(screen.getByTestId('tile-13')).toBeInTheDocument()
    expect(screen.queryByTestId('tile-1')).toBeNull()
  })

  it('calls onCameraSelect when a tile is clicked', () => {
    const onSelect = vi.fn()
    render(<CameraGrid cameras={cameras} focusedCameraId={null} onCameraSelect={onSelect} />)
    fireEvent.click(screen.getByTestId('tile-3'))
    expect(onSelect).toHaveBeenCalledWith(3)
  })

  it('marks the focused camera tile as pressed', () => {
    render(<CameraGrid cameras={cameras} focusedCameraId={2} onCameraSelect={vi.fn()} />)
    const tile = screen.getByTestId('tile-2')
    expect(tile).toHaveAttribute('aria-pressed', 'true')
  })

  it('advances page on ArrowRight key', () => {
    render(<CameraGrid cameras={cameras} focusedCameraId={null} onCameraSelect={vi.fn()} />)
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(screen.getByTestId('tile-13')).toBeInTheDocument()
  })

  it('does not go below page 0 on ArrowLeft', () => {
    render(<CameraGrid cameras={cameras} focusedCameraId={null} onCameraSelect={vi.fn()} />)
    fireEvent.keyDown(window, { key: 'ArrowLeft' })
    expect(screen.getByTestId('tile-1')).toBeInTheDocument()
  })

  it('Escape returns to the focused camera page', () => {
    render(<CameraGrid cameras={cameras} focusedCameraId={1} onCameraSelect={vi.fn()} />)
    // Go to next page first
    fireEvent.keyDown(window, { key: 'ArrowRight' })
    expect(screen.getByTestId('tile-13')).toBeInTheDocument()
    // Esc should jump back to page 0 where camera 1 is
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(screen.getByTestId('tile-1')).toBeInTheDocument()
  })
})
