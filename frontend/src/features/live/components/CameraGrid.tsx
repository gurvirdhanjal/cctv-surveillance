import { useState, useEffect, useCallback } from 'react'
import { CameraTile } from './CameraTile'
import type { CameraState } from '../types'

const PAGE_SIZE = 12

interface CameraGridProps {
  cameras: CameraState[]
  focusedCameraId: number | null
  onCameraSelect: (id: number) => void
}

export function CameraGrid({ cameras, focusedCameraId, onCameraSelect }: CameraGridProps) {
  const [page, setPage] = useState(0)
  const totalPages = Math.max(1, Math.ceil(cameras.length / PAGE_SIZE))

  const visible = cameras.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  // When focused camera changes, jump to the page that contains it
  useEffect(() => {
    if (focusedCameraId === null) return
    const idx = cameras.findIndex((c) => c.camera_id === focusedCameraId)
    if (idx >= 0) {
      const targetPage = Math.floor(idx / PAGE_SIZE)
      setPage(targetPage)
    }
  }, [focusedCameraId, cameras])

  const goToFocusedPage = useCallback(() => {
    if (focusedCameraId === null) return
    const idx = cameras.findIndex((c) => c.camera_id === focusedCameraId)
    if (idx >= 0) setPage(Math.floor(idx / PAGE_SIZE))
  }, [cameras, focusedCameraId])

  // Keyboard navigation: ←/→ paginate, Esc returns to focused tile's page
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'ArrowLeft') {
        setPage((p) => Math.max(0, p - 1))
      } else if (e.key === 'ArrowRight') {
        setPage((p) => Math.min(totalPages - 1, p + 1))
      } else if (e.key === 'Escape') {
        goToFocusedPage()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [totalPages, goToFocusedPage])

  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-4 gap-1.5">
        {visible.map((cam) => (
          <CameraTile
            key={cam.camera_id}
            camera={cam}
            isFocused={cam.camera_id === focusedCameraId}
            onSelect={() => onCameraSelect(cam.camera_id)}
          />
        ))}
      </div>

      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2 pt-1">
          <button
            type="button"
            className="rounded p-1 text-text-muted hover:text-text-primary disabled:opacity-30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            aria-label="Previous page"
          >
            ←
          </button>
          <span className="text-[12px] text-text-muted">
            {page + 1} / {totalPages}
          </span>
          <button
            type="button"
            className="rounded p-1 text-text-muted hover:text-text-primary disabled:opacity-30 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page === totalPages - 1}
            aria-label="Next page"
          >
            →
          </button>
        </div>
      )}
    </div>
  )
}
