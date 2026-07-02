import { vi, describe, it, expect, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

// Mock modules before imports
vi.mock('@/shared/api/socket', () => ({
  getSocket: vi.fn(),
}))

vi.mock('../socketDispatch', () => ({
  attachSocketDispatch: vi.fn(() => vi.fn()),
}))

vi.mock('@/shared/api/client', () => ({
  api: { get: vi.fn() },
}))

import { getSocket } from '@/shared/api/socket'
import { api } from '@/shared/api/client'
import { useLiveStore } from '../store/liveStore'
import { useSocketConnection } from './useSocketConnection'

function makeSocket() {
  const handlers: Record<string, ((...args: unknown[]) => void)[]> = {}
  return {
    on: vi.fn((event: string, h: (...args: unknown[]) => void) => {
      ;(handlers[event] ??= []).push(h)
    }),
    off: vi.fn((event: string, h: (...args: unknown[]) => void) => {
      handlers[event] = (handlers[event] ?? []).filter((x) => x !== h)
    }),
    emit: vi.fn(),
    fire: (event: string, ...args: unknown[]) => {
      handlers[event]?.forEach((h) => h(...args))
    },
  }
}

describe('useSocketConnection', () => {
  let socket: ReturnType<typeof makeSocket>

  beforeEach(() => {
    socket = makeSocket()
    vi.mocked(getSocket).mockReturnValue(socket as never)
    vi.mocked(api.get).mockResolvedValue({
      cameras: [],
      active_alerts: [],
      head_count: { plant_total: 0, by_zone: {} },
      degraded: null,
    })
    useLiveStore.setState({ degraded: null, focusedCameraId: null, followedTrackId: null })
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  it('registers connect and disconnect handlers on mount', () => {
    renderHook(() => useSocketConnection())
    expect(socket.on).toHaveBeenCalledWith('connect', expect.any(Function))
    expect(socket.on).toHaveBeenCalledWith('disconnect', expect.any(Function))
  })

  it('on connect: fetches snapshot and resets store', async () => {
    renderHook(() => useSocketConnection())
    await act(async () => {
      socket.fire('connect')
      await Promise.resolve()
    })
    expect(api.get).toHaveBeenCalledWith('/api/state/snapshot')
  })

  it('on connect: clears degraded state immediately', async () => {
    useLiveStore.setState({ degraded: { connection: 'lost' } })
    renderHook(() => useSocketConnection())
    await act(async () => {
      socket.fire('connect')
      await Promise.resolve()
    })
    expect(useLiveStore.getState().degraded).toBeNull()
  })

  it('on connect: re-emits subscribe_camera when camera is focused', async () => {
    useLiveStore.setState({ focusedCameraId: 7 })
    renderHook(() => useSocketConnection())
    await act(async () => {
      socket.fire('connect')
      await Promise.resolve()
    })
    expect(socket.emit).toHaveBeenCalledWith('subscribe_camera', { camera_id: 7 })
  })

  it('on connect: re-emits subscribe_track when track is followed', async () => {
    useLiveStore.setState({ followedTrackId: 'gtrack-42' })
    renderHook(() => useSocketConnection())
    await act(async () => {
      socket.fire('connect')
      await Promise.resolve()
    })
    expect(socket.emit).toHaveBeenCalledWith('subscribe_track', { global_track_id: 'gtrack-42' })
  })

  it('disconnect does not set degraded before 3s delay', () => {
    renderHook(() => useSocketConnection())
    socket.fire('disconnect')
    expect(useLiveStore.getState().degraded).toBeNull()
  })

  it('disconnect sets degraded after 3s', () => {
    renderHook(() => useSocketConnection())
    socket.fire('disconnect')
    act(() => { vi.advanceTimersByTime(3000) })
    expect(useLiveStore.getState().degraded).toEqual({ connection: 'lost' })
  })

  it('reconnect before 3s cancels the degraded timer', async () => {
    renderHook(() => useSocketConnection())
    socket.fire('disconnect')
    act(() => { vi.advanceTimersByTime(1000) })
    await act(async () => {
      socket.fire('connect')
      await Promise.resolve()
    })
    act(() => { vi.advanceTimersByTime(3000) })
    expect(useLiveStore.getState().degraded).toBeNull()
  })

  it('removes handlers on unmount', () => {
    const { unmount } = renderHook(() => useSocketConnection())
    unmount()
    expect(socket.off).toHaveBeenCalledWith('connect', expect.any(Function))
    expect(socket.off).toHaveBeenCalledWith('disconnect', expect.any(Function))
  })
})
