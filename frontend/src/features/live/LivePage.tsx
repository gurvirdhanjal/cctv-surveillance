import { useEffect } from 'react'
import { Helmet } from 'react-helmet-async'
import { useLiveStore } from './store/liveStore'
import { useSocketConnection } from './hooks/useSocketConnection'
import { useAuthStore } from '@/stores/authStore'
import { CameraGrid } from './components/CameraGrid'
import { FocusedCamera } from './components/FocusedCamera'
import { AlertSidebar } from './components/AlertSidebar'
import { TopBar } from './components/TopBar'
import { DegradedBanner } from './components/DegradedBanner'

export function LivePage() {
  const cameras = useLiveStore((s) => s.cameras)
  const focusedCameraId = useLiveStore((s) => s.focusedCameraId)
  const setFocusedCamera = useLiveStore((s) => s.setFocusedCamera)
  const token = useAuthStore((s) => s.token)

  useSocketConnection()

  // Auto-focus first camera when none is selected
  useEffect(() => {
    if (focusedCameraId === null && cameras.length > 0) {
      setFocusedCamera(cameras[0].camera_id)
    }
  }, [cameras, focusedCameraId, setFocusedCamera])

  const focusedMjpegUrl =
    focusedCameraId !== null && token
      ? `/api/cameras/${focusedCameraId}/mjpeg?token=${encodeURIComponent(token)}`
      : null

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
            <FocusedCamera cameraId={focusedCameraId} mjpegUrl={focusedMjpegUrl} />
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
