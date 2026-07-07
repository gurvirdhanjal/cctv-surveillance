import { useState, useEffect, useCallback, useMemo } from 'react'
import { useLiveStore } from '../store/liveStore'
import { CameraTile } from './CameraTile'
import { GridLayoutSelector } from './GridLayoutSelector'

const PAGE_SIZE = 12

export function CameraTree() {
  const cameras = useLiveStore((s) => s.cameras)
  const focusedCameraId = useLiveStore((s) => s.focusedCameraId)
  const alerts = useLiveStore((s) => s.alerts)
  const setFocusedCamera = useLiveStore((s) => s.setFocusedCamera)

  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)

  const alarmingCameraIds = useMemo(() => {
    const ids = new Set<number>()
    for (const a of alerts) {
      if (a.state === 'OPEN' && a.camera_id !== null) ids.add(a.camera_id)
    }
    return ids
  }, [alerts])

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim()
    return q ? cameras.filter((c) => c.name.toLowerCase().includes(q)) : cameras
  }, [cameras, search])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const visible = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  // Jump to page containing focused camera
  useEffect(() => {
    if (focusedCameraId === null) return
    const idx = filtered.findIndex((c) => c.camera_id === focusedCameraId)
    if (idx >= 0) setPage(Math.floor(idx / PAGE_SIZE))
  }, [focusedCameraId, filtered])

  // Reset page when search changes
  useEffect(() => setPage(0), [search])

  const goToFocusedPage = useCallback(() => {
    if (focusedCameraId === null) return
    const idx = filtered.findIndex((c) => c.camera_id === focusedCameraId)
    if (idx >= 0) setPage(Math.floor(idx / PAGE_SIZE))
  }, [filtered, focusedCameraId])

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') goToFocusedPage()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [goToFocusedPage])

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Header */}
      <div className="flex flex-shrink-0 items-center gap-2 border-b border-[#1e293b] p-2">
        <input
          type="search"
          placeholder="Search cameras…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-9 min-w-0 flex-1 rounded-[10px] border border-[#1e293b] bg-[#1a2234] px-2.5 text-[13px] text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-[var(--focus-ring)]"
          aria-label="Search cameras"
        />
        <GridLayoutSelector />
      </div>

      {/* Tile grid */}
      <div className="flex-1 overflow-y-auto p-2">
        {filtered.length === 0 ? (
          <p className="py-8 text-center text-[13px] text-slate-500">No cameras found</p>
        ) : (
          <div className="grid grid-cols-4 gap-1.5">
            {visible.map((cam) => (
              <CameraTile
                key={cam.camera_id}
                camera={cam}
                isFocused={cam.camera_id === focusedCameraId}
                isAlarming={alarmingCameraIds.has(cam.camera_id)}
                onSelect={() => setFocusedCamera(cam.camera_id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Pager */}
      {totalPages > 1 && (
        <div className="flex flex-shrink-0 items-center justify-center gap-2 border-t border-[#1e293b] py-1.5">
          <button
            type="button"
            className="rounded px-2 py-1 text-[12px] text-slate-400 disabled:opacity-30 hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            aria-label="Previous page"
          >
            Prev
          </button>
          <span className="font-mono text-[13px] text-slate-400">
            {page + 1} / {totalPages}
          </span>
          <button
            type="button"
            className="rounded px-2 py-1 text-[12px] text-slate-400 disabled:opacity-30 hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page === totalPages - 1}
            aria-label="Next page"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
