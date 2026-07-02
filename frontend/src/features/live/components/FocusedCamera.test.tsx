import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useLiveStore } from '../store/liveStore'

vi.mock('./BboxOverlay', () => ({
  BboxOverlay: vi.fn(() => null),
}))

const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
  vi.clearAllMocks()
})

const { FocusedCamera } = await import('./FocusedCamera')

describe('FocusedCamera', () => {
  it('shows select-camera placeholder when mjpegUrl is null', () => {
    render(<FocusedCamera cameraId={1} mjpegUrl={null} />)
    expect(screen.getByText('Select a camera')).toBeInTheDocument()
  })

  it('renders an img element when mjpegUrl is provided', () => {
    render(<FocusedCamera cameraId={1} mjpegUrl="/api/cameras/1/mjpeg?token=abc" />)
    expect(screen.getByRole('img', { name: 'Camera live feed' })).toBeInTheDocument()
  })

  it('img src matches the provided mjpegUrl', () => {
    const url = '/api/cameras/1/mjpeg?token=abc'
    render(<FocusedCamera cameraId={1} mjpegUrl={url} />)
    expect(screen.getByRole('img', { name: 'Camera live feed' })).toHaveAttribute('src', url)
  })

  it('shows placeholder state when no URL regardless of cameraId', () => {
    render(<FocusedCamera cameraId={null} mjpegUrl={null} />)
    expect(screen.getByText('Select a camera')).toBeInTheDocument()
  })
})
