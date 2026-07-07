import { useEffect } from 'react'
import { useLiveStore } from '../store/liveStore'
import { useCommandPaletteStore } from '@/stores/commandPaletteStore'

function isTypingTarget(e: KeyboardEvent): boolean {
  const target = e.target as HTMLElement
  return (
    target.tagName === 'INPUT' ||
    target.tagName === 'TEXTAREA' ||
    target.isContentEditable
  )
}

interface UseLiveShortcutsOptions {
  onExport?: () => void
  onToggleLegend?: () => void
}

export function useLiveShortcuts({
  onExport,
  onToggleLegend,
}: UseLiveShortcutsOptions = {}) {
  const paletteOpen = useCommandPaletteStore((s) => s.open)

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (isTypingTarget(e)) return
      if (paletteOpen) return
      // Ignore Cmd/Ctrl+K (palette) and other modifier combos
      if (e.metaKey || e.ctrlKey || e.altKey) return

      const state = useLiveStore.getState()

      switch (e.key.toLowerCase()) {
        case 'a': {
          const first = state.alerts.find((a) => a.state === 'OPEN')
          if (first) {
            e.preventDefault()
            state.acknowledgeAlert(first.alert_id)
          }
          break
        }
        case 'r': {
          const first = state.alerts.find((a) => a.state === 'OPEN')
          if (first) {
            e.preventDefault()
            state.resolveAlert(first.alert_id)
          }
          break
        }
        case 'b': {
          if (state.focusedCameraId !== null) {
            e.preventDefault()
            state.addBookmark({ cameraId: state.focusedCameraId, tsMs: Date.now() })
          }
          break
        }
        case 'e': {
          e.preventDefault()
          onExport?.()
          break
        }
        case 'n': {
          e.preventDefault()
          const cams = state.cameras
          if (cams.length === 0) break
          const idx = cams.findIndex((c) => c.camera_id === state.focusedCameraId)
          const next = cams[(idx + 1) % cams.length]
          if (next) state.setFocusedCamera(next.camera_id)
          break
        }
        case 'f': {
          // Toggle follow on focused camera's first tracked person
          e.preventDefault()
          if (state.followedTrackId !== null) {
            state.setFollowedTrack(null)
          }
          break
        }
        case '?': {
          e.preventDefault()
          onToggleLegend?.()
          break
        }
        default:
          break
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [paletteOpen, onExport, onToggleLegend])
}
