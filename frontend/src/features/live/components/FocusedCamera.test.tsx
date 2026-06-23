import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useLiveStore } from '../store/liveStore'

// vi.hoisted ensures variables are available when vi.mock factories run
const { MockHls, mockHlsLoadSource, mockHlsAttachMedia } = vi.hoisted(() => {
  const mockHlsDestroy = vi.fn()
  const mockHlsLoadSource = vi.fn()
  const mockHlsAttachMedia = vi.fn()
  const MockHls = vi.fn(() => ({
    loadSource: mockHlsLoadSource,
    attachMedia: mockHlsAttachMedia,
    destroy: mockHlsDestroy,
  }))
  Object.assign(MockHls, { isSupported: vi.fn(() => true) })
  return { MockHls, mockHlsLoadSource, mockHlsAttachMedia }
})

vi.mock('hls.js', () => ({ default: MockHls }))

vi.mock('./BboxOverlay', () => ({
  BboxOverlay: vi.fn(() => null),
}))

const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
  vi.clearAllMocks()
})

// Lazy-import FocusedCamera AFTER mocks are set up
const { FocusedCamera } = await import('./FocusedCamera')

describe('FocusedCamera', () => {
  it('shows stream unavailable when hlsUrl is null', () => {
    render(<FocusedCamera cameraId={1} hlsUrl={null} />)
    expect(screen.getByText('Stream unavailable')).toBeInTheDocument()
  })

  it('renders a video element when hlsUrl is provided', () => {
    render(<FocusedCamera cameraId={1} hlsUrl="http://stream/cam1.m3u8" />)
    expect(screen.getByLabelText('Camera feed')).toBeInTheDocument()
  })

  it('attaches HLS.js to the video element when hlsUrl provided', () => {
    render(<FocusedCamera cameraId={1} hlsUrl="http://stream/cam1.m3u8" />)
    expect(MockHls).toHaveBeenCalledOnce()
    expect(mockHlsLoadSource).toHaveBeenCalledWith('http://stream/cam1.m3u8')
    expect(mockHlsAttachMedia).toHaveBeenCalledOnce()
  })

  it('shows unavailable state when no URL regardless of cameraId', () => {
    render(<FocusedCamera cameraId={null} hlsUrl={null} />)
    expect(screen.getByText('Stream unavailable')).toBeInTheDocument()
  })
})
