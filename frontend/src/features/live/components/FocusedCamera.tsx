import { useState, useRef, useCallback, useEffect } from 'react'
import { Maximize2, Minimize2, Bookmark, Download } from 'lucide-react'
import { BoundingBoxOverlay } from './BoundingBoxOverlay'
import { useHlsStream } from '../hooks/useHlsStream'
import { useLiveStore } from '../store/liveStore'
import { useAuthStore } from '@/stores/authStore'

interface FocusedCameraProps {
  cameraId: number | null
  mjpegUrl: string | null
}

export function FocusedCamera({ cameraId, mjpegUrl }: FocusedCameraProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [controlsVisible, setControlsVisible] = useState(false)
  const [streamError, setStreamError] = useState(false)
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const addBookmark = useLiveStore((s) => s.addBookmark)
  const token = useAuthStore((s) => s.token)

  // HLS stream URL — construct manifest URL when token is present
  const hlsManifestUrl =
    cameraId !== null && token
      ? `/api/cameras/${cameraId}/hls/index.m3u8?token=${encodeURIComponent(token)}`
      : null

  // Use HLS for the <video> element (separate from MJPEG fallback)
  useHlsStream(hlsManifestUrl, videoRef)

  // Reset stream error on camera change
  useEffect(() => setStreamError(false), [cameraId])

  // Track fullscreen state
  useEffect(() => {
    function onFullscreenChange() {
      setIsFullscreen(Boolean(document.fullscreenElement))
    }
    document.addEventListener('fullscreenchange', onFullscreenChange)
    return () => document.removeEventListener('fullscreenchange', onFullscreenChange)
  }, [])

  const showControls = useCallback(() => {
    setControlsVisible(true)
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current)
    hideTimerRef.current = setTimeout(() => setControlsVisible(false), 2500)
  }, [])

  const toggleFullscreen = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    if (!document.fullscreenElement) {
      void el.requestFullscreen()
    } else {
      void document.exitFullscreen()
    }
  }, [])

  const handleBookmark = useCallback(() => {
    if (cameraId !== null) {
      addBookmark({ cameraId, tsMs: Date.now() })
    }
  }, [cameraId, addBookmark])

  if (!cameraId) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-[#0a0e1a]">
        <div className="text-center">
          <svg
            className="mx-auto mb-3 h-10 w-10 text-slate-600"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M15 10l4.553-2.069A1 1 0 0121 8.82v6.36a1 1 0 01-1.447.89L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"
            />
          </svg>
          <p className="text-[13px] text-slate-500">Select a camera</p>
        </div>
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      className="relative h-full w-full bg-black"
      onMouseMove={showControls}
      onFocus={showControls}
    >
      {/* MJPEG stream fallback (primary path until HLS is confirmed working) */}
      {mjpegUrl && !streamError ? (
        <img
          src={mjpegUrl}
          className="h-full w-full object-contain"
          alt={`Camera ${cameraId} live feed`}
          onError={() => setStreamError(true)}
        />
      ) : (
        <video
          ref={videoRef}
          className="h-full w-full object-contain"
          aria-label={`Camera ${cameraId} HLS live feed`}
          muted
          playsInline
        />
      )}

      {cameraId !== null && <BoundingBoxOverlay cameraId={cameraId} />}

      {/* Controls overlay */}
      <div
        className={`absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/70 to-transparent px-3 pb-3 pt-6 transition-opacity duration-200 ${controlsVisible ? 'opacity-100' : 'opacity-0'}`}
        aria-hidden={!controlsVisible}
      >
        <div className="flex items-center gap-2">
          <div className="flex-1" />
          <button
            type="button"
            className="rounded-[10px] bg-[#1a2234]/80 p-1.5 text-slate-300 hover:bg-[#232d42] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
            onClick={handleBookmark}
            aria-label="Bookmark this frame"
            tabIndex={controlsVisible ? 0 : -1}
          >
            <Bookmark className="h-4 w-4" />
          </button>
          <button
            type="button"
            className="rounded-[10px] bg-[#1a2234]/80 p-1.5 text-slate-300 hover:bg-[#232d42] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
            onClick={toggleFullscreen}
            aria-label={isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen'}
            tabIndex={controlsVisible ? 0 : -1}
          >
            {isFullscreen ? (
              <Minimize2 className="h-4 w-4" />
            ) : (
              <Maximize2 className="h-4 w-4" />
            )}
          </button>
          <button
            type="button"
            className="rounded-[10px] bg-[#1a2234]/80 p-1.5 text-slate-300 hover:bg-[#232d42] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
            aria-label="Export clip"
            tabIndex={controlsVisible ? 0 : -1}
          >
            <Download className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
