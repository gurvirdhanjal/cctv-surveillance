import { useState, useEffect } from 'react'
import { useLiveStore } from '../store/liveStore'
import { useAuthStore } from '@/stores/authStore'

/**
 * Returns a cache-busting snapshot URL for the given camera, refreshing every
 * 2 s normally or 5 s in degraded mode (§10).
 * Includes ?token= so the <img> tag can auth without a custom header.
 */
export function useCameraSnapshot(cameraId: number | null): string | null {
  const degraded = useLiveStore((s) => s.degraded)
  const token = useAuthStore((s) => s.token)
  const intervalMs = degraded ? 5000 : 2000
  const [ts, setTs] = useState<number>(() => Date.now())

  useEffect(() => {
    if (cameraId === null) return
    const id = setInterval(() => setTs(Date.now()), intervalMs)
    return () => clearInterval(id)
  }, [cameraId, intervalMs])

  if (cameraId === null || !token) return null
  return `/api/cameras/${cameraId}/snapshot?t=${ts}&token=${encodeURIComponent(token)}`
}
