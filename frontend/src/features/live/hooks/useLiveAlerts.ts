import { useEffect, useCallback } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { AlertResponse, AlertState } from '@/shared/api/types'
import { useLiveStore } from '../store/liveStore'
import type { LiveAlert } from '../types'

function toLiveAlert(a: AlertResponse): LiveAlert {
  return { ...a, global_track_id: null, snapshot_url: null }
}

/**
 * Seeds liveStore.alerts from `GET /api/alerts?state=OPEN` and exposes
 * acknowledge / resolve mutations with optimistic updates.
 *
 * Socket event handlers (applyAlertFired, applyAlertStateChanged) are also
 * re-exported here so 4F can wire them from the socket dispatch layer.
 */
export function useLiveAlerts() {
  const applyAlertFired = useLiveStore((s) => s.applyAlertFired)
  const applyAlertStateChanged = useLiveStore((s) => s.applyAlertStateChanged)
  const queryClient = useQueryClient()

  const { data: fetchedAlerts } = useQuery({
    queryKey: ['alerts', 'active'],
    queryFn: () => api.get<AlertResponse[]>('/api/alerts?state=OPEN'),
    staleTime: 5000,
  })

  // Seed store whenever REST data arrives
  useEffect(() => {
    if (fetchedAlerts) {
      useLiveStore.setState({ alerts: fetchedAlerts.map(toLiveAlert) })
    }
  }, [fetchedAlerts])

  const acknowledge = useCallback(
    async (alertId: number) => {
      applyAlertStateChanged(alertId, 'ACKNOWLEDGED' as AlertState)
      try {
        await api.patch(`/api/alerts/${alertId}`, { state: 'ACKNOWLEDGED' })
        void queryClient.invalidateQueries({ queryKey: ['alerts'] })
      } catch {
        applyAlertStateChanged(alertId, 'OPEN' as AlertState)
      }
    },
    [applyAlertStateChanged, queryClient],
  )

  const resolve = useCallback(
    async (alertId: number) => {
      applyAlertStateChanged(alertId, 'RESOLVED' as AlertState)
      try {
        await api.patch(`/api/alerts/${alertId}`, { state: 'RESOLVED' })
        void queryClient.invalidateQueries({ queryKey: ['alerts'] })
      } catch {
        applyAlertStateChanged(alertId, 'OPEN' as AlertState)
      }
    },
    [applyAlertStateChanged, queryClient],
  )

  return { acknowledge, resolve, applyAlertFired, applyAlertStateChanged }
}
