import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useLiveStore } from '../store/liveStore'

vi.mock('./BoundingBoxOverlay', () => ({
  BoundingBoxOverlay: vi.fn(() => null),
}))

vi.mock('../hooks/useHlsStream', () => ({
  useHlsStream: vi.fn(),
}))

vi.mock('@/stores/authStore', () => ({
  useAuthStore: vi.fn((sel: (s: { token: string | null }) => unknown) => sel({ token: 'tok' })),
}))

const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
  vi.clearAllMocks()
})

const { FocusedCamera } = await import('./FocusedCamera')

describe('FocusedCamera', () => {
  it('shows "Select a camera" when cameraId is null', () => {
    render(<FocusedCamera cameraId={null} mjpegUrl={null} />)
    expect(screen.getByText('Select a camera')).toBeInTheDocument()
  })

  it('renders an img when mjpegUrl is provided', () => {
    render(<FocusedCamera cameraId={1} mjpegUrl="/api/cameras/1/mjpeg?token=abc" />)
    expect(screen.getByRole('img', { name: 'Camera 1 live feed' })).toBeInTheDocument()
  })

  it('img src matches the provided mjpegUrl', () => {
    const url = '/api/cameras/1/mjpeg?token=abc'
    render(<FocusedCamera cameraId={1} mjpegUrl={url} />)
    expect(screen.getByRole('img', { name: 'Camera 1 live feed' })).toHaveAttribute('src', url)
  })

  it('renders video element when cameraId set but no mjpegUrl', () => {
    const { container } = render(<FocusedCamera cameraId={1} mjpegUrl={null} />)
    expect(container.querySelector('video')).toBeTruthy()
    expect(screen.queryByText('Select a camera')).toBeNull()
  })
})
