import { useLiveStore } from '../store/liveStore'
import type { PersonLocation } from '../types'

/**
 * Returns tracked persons from the live store.
 * Optionally filters by cameraId for per-camera overlays.
 */
export function useTrackedPersons(cameraId?: number): PersonLocation[] {
  const trackedPersons = useLiveStore((s) => s.trackedPersons)
  const all = Array.from(trackedPersons.values())
  return cameraId === undefined ? all : all.filter((loc) => loc.camera_id === cameraId)
}
