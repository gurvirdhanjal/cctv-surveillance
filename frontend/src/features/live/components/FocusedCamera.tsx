import { useState, useEffect, useRef } from 'react'
import { BboxOverlay } from './BboxOverlay'

interface FocusedCameraProps {
  cameraId: number | null
  mjpegUrl: string | null
}

// How long to wait for the first frame before declaring stream unavailable
const STREAM_CONNECT_TIMEOUT_MS = 8000

export function FocusedCamera({ cameraId, mjpegUrl }: FocusedCameraProps) {
  const [streamError, setStreamError] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    setStreamError(false)

    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }

    if (!mjpegUrl) return

    // If the first frame doesn't arrive within the timeout, show error state.
    // onLoad fires for each frame of the MJPEG stream, so this clears once
    // any frame arrives.
    timeoutRef.current = setTimeout(() => {
      setStreamError(true)
    }, STREAM_CONNECT_TIMEOUT_MS)

    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current)
        timeoutRef.current = null
      }
    }
  }, [mjpegUrl])

  function handleLoad() {
    // First frame arrived — clear the connection timeout
    if (timeoutRef.current) {
      clearTimeout(timeoutRef.current)
      timeoutRef.current = null
    }
    setStreamError(false)
  }

  if (!mjpegUrl) {
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
          <p className="text-[13px] text-text-muted">Select a camera</p>
        </div>
      </div>
    )
  }

  if (streamError) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center bg-surface-sunken">
        <svg
          className="mb-3 h-10 w-10 text-text-muted"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"
          />
        </svg>
        <p className="text-[13px] font-medium text-text-secondary">Stream unavailable</p>
        <p className="mt-1 text-[12px] text-text-muted">Check camera connection and status</p>
      </div>
    )
  }

  return (
    <div className="relative h-full w-full bg-black">
      <img
        src={mjpegUrl}
        className="h-full w-full object-contain"
        alt="Camera live feed"
        onError={() => setStreamError(true)}
        onLoad={handleLoad}
      />
      {cameraId !== null && <BboxOverlay cameraId={cameraId} />}
    </div>
  )
}
