import { useEffect, useRef } from 'react'
import Hls from 'hls.js'
import { BboxOverlay } from './BboxOverlay'

interface FocusedCameraProps {
  cameraId: number | null
  hlsUrl: string | null
}

/**
 * Renders an HLS video feed for the focused camera.
 * Falls back to a "stream unavailable" placeholder when no HLS URL is configured
 * (e.g. before the RTSP→HLS transcoder is deployed — Phase 6).
 */
export function FocusedCamera({ cameraId, hlsUrl }: FocusedCameraProps) {
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    const video = videoRef.current
    if (!video || !hlsUrl) return

    if (Hls.isSupported()) {
      const hls = new Hls({ startLevel: -1 })
      hls.loadSource(hlsUrl)
      hls.attachMedia(video)
      return () => hls.destroy()
    }

    // Native HLS support (Safari)
    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = hlsUrl
    }
  }, [hlsUrl])

  if (!hlsUrl) {
    return (
      <div className="flex h-full w-full items-center justify-center bg-surface-sunken">
        <div className="text-center">
          <svg
            className="mx-auto mb-3 h-10 w-10 text-text-muted"
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
          <p className="text-[13px] text-text-muted">Stream unavailable</p>
        </div>
      </div>
    )
  }

  return (
    <div className="relative h-full w-full bg-black">
      <video
        ref={videoRef}
        className="h-full w-full"
        autoPlay
        muted
        playsInline
        aria-label="Camera feed"
      />
      {cameraId !== null && <BboxOverlay cameraId={cameraId} />}
    </div>
  )
}
