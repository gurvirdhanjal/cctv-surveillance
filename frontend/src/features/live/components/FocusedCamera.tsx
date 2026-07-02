import { BboxOverlay } from './BboxOverlay'

interface FocusedCameraProps {
  cameraId: number | null
  mjpegUrl: string | null
}

export function FocusedCamera({ cameraId, mjpegUrl }: FocusedCameraProps) {
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

  return (
    <div className="relative h-full w-full bg-black">
      {/* MJPEG stream — browser renders multipart/x-mixed-replace natively */}
      <img
        key={mjpegUrl}
        src={mjpegUrl}
        className="h-full w-full object-contain"
        alt="Camera live feed"
      />
      {cameraId !== null && <BboxOverlay cameraId={cameraId} />}
    </div>
  )
}
