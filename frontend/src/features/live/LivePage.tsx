import { useEffect, useState, useCallback } from 'react'
import { Helmet } from 'react-helmet-async'
import { Group, Panel, Separator } from 'react-resizable-panels'
import { useLiveStore } from './store/liveStore'
import { useSocketConnection } from './hooks/useSocketConnection'
import { useAuthStore } from '@/stores/authStore'
import { useWorkspacePrefs } from '@/shared/workspace/useWorkspacePrefs'
import { CameraTree } from './components/CameraTree'
import { FocusedCamera } from './components/FocusedCamera'
import { AlertSidebar } from './components/AlertSidebar'
import { AlertTimeline } from './components/AlertTimeline'
import { TopBar } from './components/TopBar'
import { OfflineReconnectBanner } from './components/OfflineReconnectBanner'
import { SystemStatusStrip } from './components/SystemStatusStrip'
import { ShortcutLegend } from './components/ShortcutLegend'
import { ClipExportDialog } from './components/ClipExportDialog'
import { useLiveShortcuts } from './hooks/useLiveShortcuts'

const PANEL_KEY = 'live-main'

export function LivePage() {
  const cameras = useLiveStore((s) => s.cameras)
  const focusedCameraId = useLiveStore((s) => s.focusedCameraId)
  const setFocusedCamera = useLiveStore((s) => s.setFocusedCamera)
  const token = useAuthStore((s) => s.token)

  const [legendOpen, setLegendOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)

  const savedPanelSizes = useWorkspacePrefs((s) => s.panelLayouts[PANEL_KEY])
  const setPanelLayout = useWorkspacePrefs((s) => s.setPanelLayout)

  useSocketConnection()

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

  const handleLayout = useCallback(
    (layout: Array<{ sizePixels: number; sizePercentage: number }>) => {
      setPanelLayout(PANEL_KEY, layout.map((l) => l.sizePercentage))
    },
    [setPanelLayout],
  )

  return (
    <>
      <Helmet title="Live" />
      <div
        data-theme="dark"
        className="flex h-screen flex-col overflow-hidden bg-[#0a0e1a] text-slate-100"
      >
        <TopBar />
        <OfflineReconnectBanner />

        <div className="min-h-0 flex-1">
          <Group
            orientation="horizontal"
            onLayoutChange={handleLayout}
            {...(savedPanelSizes ? { defaultLayout: savedPanelSizes } : {})}
            style={{ height: '100%' }}
          >
            <Panel
              id="camera-tree"
              defaultSize={22}
              minSize={16}
            >
              <section
                aria-label="Camera list"
                className="h-full overflow-hidden border-r border-[#1e293b] bg-[#111827]"
              >
                <CameraTree />
              </section>
            </Panel>

            <Separator className="w-px bg-[#1e293b] hover:bg-brand-500/60 transition-colors" />

            <Panel id="focused">
              <section
                aria-label="Focused camera"
                className="relative h-full min-w-0 bg-[#0a0e1a]"
              >
                <FocusedCamera cameraId={focusedCameraId} mjpegUrl={focusedMjpegUrl} />
              </section>
            </Panel>

            <Separator className="w-px bg-[#1e293b] hover:bg-brand-500/60 transition-colors" />

            <Panel
              id="alerts"
              defaultSize={26}
              minSize={20}
            >
              <section
                aria-label="Alerts"
                className="h-full overflow-hidden border-l border-[#1e293b] bg-[#111827]"
              >
                <AlertSidebar />
              </section>
            </Panel>
          </Group>
        </div>

        {/* §I: 120px alert timeline row */}
        <AlertTimeline />

        {/* §I: 28px status bar */}
        <SystemStatusStrip />

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
