import { useState, useEffect } from 'react'
import { useLiveStore } from '../store/liveStore'

/**
 * Returns a cache-busting snapshot URL for the given camera, refreshing every
 * 2 s normally or 5 s in degraded mode (§10).
 */
export function useCameraSnapshot(cameraId: number | null): string | null {
  const degraded = useLiveStore((s) => s.degraded)
  const intervalMs = degraded ? 5000 : 2000
  const [ts, setTs] = useState<number>(() => Date.now())

  useEffect(() => {
    if (cameraId === null) return
    const id = setInterval(() => setTs(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [cameraId, intervalMs])

  if (cameraId === null) return null
  return `/api/cameras/${cameraId}/snapshot?t=${ts}`
}
