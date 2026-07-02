import { useEffect, useRef } from 'react'
import { api } from '@/shared/api/client'
import { getSocket } from '@/shared/api/socket'
import { attachSocketDispatch } from '../socketDispatch'
import { useLiveStore } from '../store/liveStore'
import type { StateSnapshot } from '@/shared/api/types'

const DEGRADED_DELAY_MS = 3_000

export function useSocketConnection(): void {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    const socket = getSocket()
    const detach = attachSocketDispatch(socket)

    const onConnect = async () => {
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current)
        timerRef.current = null
      }
      useLiveStore.setState({ degraded: null })

      try {
        const snapshot = await api.get<StateSnapshot>('/api/state/snapshot')
        useLiveStore.getState().reset(snapshot)
      } catch {
        // snapshot failure is non-fatal — UI keeps last-known state
      }

      const { focusedCameraId, followedTrackId } = useLiveStore.getState()
      if (focusedCameraId !== null) {
        socket.emit('subscribe_camera', { camera_id: focusedCameraId })
      }
      if (followedTrackId !== null) {
        socket.emit('subscribe_track', { global_track_id: followedTrackId })
      }
    }

    const onDisconnect = () => {
      timerRef.current = setTimeout(() => {
        useLiveStore.setState({ degraded: { connection: 'lost' } })
      }, DEGRADED_DELAY_MS)
    }

    socket.on('connect', onConnect)
    socket.on('disconnect', onDisconnect)

    return () => {
      socket.off('connect', onConnect)
      socket.off('disconnect', onDisconnect)
      detach()
      if (timerRef.current !== null) {
        clearTimeout(timerRef.current)
      }
    }
  }, [])
}
