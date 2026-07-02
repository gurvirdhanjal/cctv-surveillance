import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useCameraSnapshot } from './useCameraSnapshot'
import { useLiveStore } from '../store/liveStore'
import { useAuthStore } from '@/stores/authStore'

const FAKE_TOKEN = 'eyJ.test.token'

const initialLiveState = useLiveStore.getState()
const initialAuthState = useAuthStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialLiveState, true)
  useAuthStore.setState({ ...initialAuthState, token: FAKE_TOKEN }, true)
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useCameraSnapshot', () => {
  it('returns null when cameraId is null', () => {
    const { result } = renderHook(() => useCameraSnapshot(null))
    expect(result.current).toBeNull()
  })

  it('returns null when there is no auth token', () => {
    useAuthStore.setState({ ...initialAuthState, token: null }, true)
    const { result } = renderHook(() => useCameraSnapshot(7))
    expect(result.current).toBeNull()
  })

  it('returns a URL containing the camera ID', () => {
    const { result } = renderHook(() => useCameraSnapshot(7))
    expect(result.current).toMatch(/\/api\/cameras\/7\/snapshot/)
  })

  it('includes a timestamp query param', () => {
    const { result } = renderHook(() => useCameraSnapshot(7))
    expect(result.current).toMatch(/\?t=\d+/)
  })

  it('includes the auth token as a query param', () => {
    const { result } = renderHook(() => useCameraSnapshot(7))
    expect(result.current).toContain(`token=${encodeURIComponent(FAKE_TOKEN)}`)
  })

  it('updates the URL after each 2 s interval', () => {
    const { result } = renderHook(() => useCameraSnapshot(5))
    const first = result.current

    act(() => {
      vi.advanceTimersByTime(2000)
    })

    expect(result.current).not.toBe(first)
    expect(result.current).toMatch(/\/api\/cameras\/5\/snapshot/)
  })

  it('uses 5 s interval in degraded mode', () => {
    useLiveStore.setState({ degraded: { connection: 'lost' } })
    const { result } = renderHook(() => useCameraSnapshot(5))
    const first = result.current

    act(() => {
      vi.advanceTimersByTime(2000)
    })
    expect(result.current).toBe(first)

    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(result.current).not.toBe(first)
  })
})
