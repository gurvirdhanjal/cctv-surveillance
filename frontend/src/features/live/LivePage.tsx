import { useEffect, useState } from 'react'
import { Helmet } from 'react-helmet-async'
import { useLiveStore } from './store/liveStore'
import { useSocketConnection } from './hooks/useSocketConnection'
import { useAuthStore } from '@/stores/authStore'
import { CameraTree } from './components/CameraTree'
import { FocusedCamera } from './components/FocusedCamera'
import { AlertSidebar } from './components/AlertSidebar'
import { TopBar } from './components/TopBar'
import { OfflineReconnectBanner } from './components/OfflineReconnectBanner'
import { SystemStatusStrip } from './components/SystemStatusStrip'
import { ShortcutLegend } from './components/ShortcutLegend'
import { ClipExportDialog } from './components/ClipExportDialog'
import { useLiveShortcuts } from './hooks/useLiveShortcuts'

export function LivePage() {
  const cameras = useLiveStore((s) => s.cameras)
  const focusedCameraId = useLiveStore((s) => s.focusedCameraId)
  const setFocusedCamera = useLiveStore((s) => s.setFocusedCamera)
  const token = useAuthStore((s) => s.token)

  const [legendOpen, setLegendOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)

  useSocketConnection()

  // Auto-focus first camera when none is selected
  useEffect(() => {
    if (focusedCameraId === null && cameras.length > 0) {
      setFocusedCamera(cameras[0].camera_id)
    }
  }, [cameras, focusedCameraId, setFocusedCamera])

  useLiveShortcuts({
    onExport: () => setExportOpen(true),
    onToggleLegend: () => setLegendOpen((v) => !v),
  })

  const focusedMjpegUrl =
    focusedCameraId !== null && token
      ? `/api/cameras/${focusedCameraId}/mjpeg?token=${encodeURIComponent(token)}`
      : null

  return (
    <>
      <Helmet title="Live" />
      {/* Forced-dark console — overrides global theme toggle */}
      <div
        data-theme="dark"
        className="flex h-screen flex-col overflow-hidden bg-[#0a0e1a] text-slate-100"
      >
        <TopBar />
        <OfflineReconnectBanner />

        <div className="grid min-h-0 flex-1" style={{ gridTemplateColumns: '320px 1fr 380px' }}>
          {/* Left: Camera tree */}
          <section
            aria-label="Camera list"
            className="overflow-hidden border-r border-[#1e293b] bg-[#111827]"
          >
            <CameraTree />
          </section>

          {/* Center: Focused camera */}
          <section
            aria-label="Focused camera"
            className="relative min-w-0 bg-[#0a0e1a]"
          >
            <FocusedCamera cameraId={focusedCameraId} mjpegUrl={focusedMjpegUrl} />
          </section>

          {/* Right: Alert sidebar */}
          <section
            aria-label="Alerts"
            className="overflow-hidden border-l border-[#1e293b] bg-[#111827]"
          >
            <AlertSidebar />
          </section>
        </div>

        <SystemStatusStrip />

        {/* Skip link target */}
        <div id="alert-sidebar-anchor" className="sr-only" tabIndex={-1} />
      </div>

      <ShortcutLegend open={legendOpen} onClose={() => setLegendOpen(false)} />
      <ClipExportDialog
        open={exportOpen}
        onClose={() => setExportOpen(false)}
        cameraId={focusedCameraId}
      />
    </>
  )
}
