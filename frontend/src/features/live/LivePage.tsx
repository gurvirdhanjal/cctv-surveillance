import { useEffect } from 'react'
import { Helmet } from 'react-helmet-async'
import { useLiveStore } from './store/liveStore'
import { useSocketConnection } from './hooks/useSocketConnection'
import { CameraGrid } from './components/CameraGrid'
import { FocusedCamera } from './components/FocusedCamera'
import { AlertSidebar } from './components/AlertSidebar'
import { TopBar } from './components/TopBar'
import { DegradedBanner } from './components/DegradedBanner'

export function LivePage() {
  const cameras = useLiveStore((s) => s.cameras)
  const focusedCameraId = useLiveStore((s) => s.focusedCameraId)
  const setFocusedCamera = useLiveStore((s) => s.setFocusedCamera)

  useSocketConnection()

  // Auto-focus first camera when none is selected
  useEffect(() => {
    if (focusedCameraId === null && cameras.length > 0) {
      setFocusedCamera(cameras[0].camera_id)
    }
  }, [cameras, focusedCameraId, setFocusedCamera])

  // HLS URL placeholder — Phase 6 will provide RTSP→HLS URLs per camera
  const focusedHlsUrl: string | null = null

  return (
    <>
      <Helmet title="Live" />
      <div className="flex h-screen flex-col overflow-hidden bg-surface-sunken">
        <TopBar />
        <DegradedBanner />
        <div className="flex min-h-0 flex-1">
          {/* Camera grid — 320px fixed */}
          <div
            className="w-[320px] flex-shrink-0 overflow-y-auto border-r border-border p-2"
            aria-label="Camera grid"
          >
            <CameraGrid
              cameras={cameras}
              focusedCameraId={focusedCameraId}
              onCameraSelect={setFocusedCamera}
            />
          </div>

          {/* Focused camera — fills remaining space */}
          <div className="relative min-w-0 flex-1">
            <FocusedCamera cameraId={focusedCameraId} hlsUrl={focusedHlsUrl} />
          </div>

          {/* Alert sidebar — 380px fixed */}
          <div
            className="w-[380px] flex-shrink-0 border-l border-border"
            aria-label="Alert sidebar"
          >
            <AlertSidebar />
          </div>
        </div>
      </div>
    </>
  )
}
