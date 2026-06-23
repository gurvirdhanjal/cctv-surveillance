import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useTrackedPersons } from './useTrackedPersons'
import { useLiveStore } from '../store/liveStore'
import type { PersonLocation } from '../types'

const initialState = useLiveStore.getState()

beforeEach(() => {
  useLiveStore.setState(initialState, true)
})

const loc = (id: string, cameraId: number): PersonLocation => ({
  global_track_id: id,
  person_id: null,
  camera_id: cameraId,
  bbox: [0, 0, 0.5, 0.5],
  floor_x: null,
  floor_y: null,
  ts: '2026-06-24T10:00:00Z',
})

describe('useTrackedPersons', () => {
  it('returns empty array when store is empty', () => {
    const { result } = renderHook(() => useTrackedPersons())
    expect(result.current).toEqual([])
  })

  it('returns all tracked persons when no filter', () => {
    useLiveStore.getState().applyLocations([loc('a', 1), loc('b', 2)])
    const { result } = renderHook(() => useTrackedPersons())
    expect(result.current).toHaveLength(2)
  })

  it('filters by cameraId when provided', () => {
    useLiveStore.getState().applyLocations([loc('a', 1), loc('b', 2), loc('c', 1)])
    const { result } = renderHook(() => useTrackedPersons(1))
    expect(result.current).toHaveLength(2)
    expect(result.current.every((p) => p.camera_id === 1)).toBe(true)
  })

  it('returns empty when no persons on the given camera', () => {
    useLiveStore.getState().applyLocations([loc('a', 1)])
    const { result } = renderHook(() => useTrackedPersons(99))
    expect(result.current).toHaveLength(0)
  })
})
