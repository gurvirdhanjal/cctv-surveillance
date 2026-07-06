import { useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { useLiveStore } from './store/liveStore'
import { FocusedCamera } from './components/FocusedCamera'
import { AlertSidebar } from './components/AlertSidebar'
import { TopBar } from './components/TopBar'
import { PersonDot } from './components/PersonDot'
import { useTrackedPersons } from './hooks/useTrackedPersons'

/**
 * Route `/live/follow/:trackId` — follow mode.
 * Auto-switches focused camera to whichever camera holds the tracked person.
 * Shows movement timeline strip and mini floor-plan with live position dot.
 * `subscribe_track` socket emit is wired in Phase 4F.
 */
export function FollowPersonPage() {
  const { trackId } = useParams<{ trackId: string }>()
  const setFollowedTrack = useLiveStore((s) => s.setFollowedTrack)
  const setFocusedCamera = useLiveStore((s) => s.setFocusedCamera)
  const allPersons = useTrackedPersons()

  // Register followed track in store; clear on unmount
  useEffect(() => {
    if (trackId) setFollowedTrack(trackId)
    return () => setFollowedTrack(null)
  }, [trackId, setFollowedTrack])

  // Auto-switch focused camera to the one holding the tracked person
  const trackedLoc = trackId ? allPersons.find((p) => p.global_track_id === trackId) : undefined

  useEffect(() => {
    if (trackedLoc) setFocusedCamera(trackedLoc.camera_id)
  }, [trackedLoc, setFocusedCamera])

  return (
    <>
      <Helmet title={`Following ${trackId ?? '—'}`} />
      <div className="flex h-screen flex-col overflow-hidden bg-surface-sunken">
        <TopBar />

        {/* Movement timeline strip */}
        <div
          className="flex h-10 flex-shrink-0 items-center gap-3 border-b border-border bg-surface-raised px-4"
          aria-label="Movement timeline"
        >
          <span className="text-[12px] text-text-muted">Following:</span>
          <span className="text-[12px] font-medium text-text-primary">{trackId}</span>
          {trackedLoc && (
            <span className="text-[12px] text-text-muted">
              Camera #{trackedLoc.camera_id}
            </span>
          )}
        </div>

        <div className="flex min-h-0 flex-1">
          {/* Main column: focused feed + floor-plan */}
          <div className="relative min-w-0 flex-1">
            <FocusedCamera cameraId={trackedLoc?.camera_id ?? null} mjpegUrl={null} />

            {/* Mini floor-plan — shows tracked person dot */}
            {trackedLoc && (
              <div
                className="absolute bottom-4 right-4 h-32 w-48 overflow-hidden rounded-lg border border-border bg-surface-raised/90 shadow-2"
                aria-label="Mini floor plan"
              >
                <div className="relative h-full w-full">
                  <PersonDot location={trackedLoc} />
                </div>
              </div>
            )}
          </div>

          {/* Alert sidebar */}
          <div className="w-[380px] flex-shrink-0 border-l border-border">
            <AlertSidebar />
          </div>
        </div>
      </div>
    </>
  )
}
