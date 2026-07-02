import { useState } from 'react'

interface Props {
  cameraId: number
  initialStep?: Step
  initialReprErr?: number | null
}

type Step = 'start' | 'pick_frame' | 'pick_floor' | 'computing' | 'review' | 'done'

type Point = [number, number]

const STEP_LABELS: Record<Step, string> = {
  start: 'Start',
  pick_frame: 'Pick Frame Points',
  pick_floor: 'Pick Floor Points',
  computing: 'Computing',
  review: 'Review',
  done: 'Done',
}

function simulateReprojError(): number {
  return 1.2
}

export function HomographyCalibrator({ cameraId: _cameraId, initialStep = 'start', initialReprErr = null }: Props) {
  const [step, setStep] = useState<Step>(initialStep)
  const [framePoints, setFramePoints] = useState<Point[]>([])
  const [floorPoints, setFloorPoints] = useState<Point[]>([])
  const [reprErr, setReprErr] = useState<number | null>(initialReprErr)

  function handleFrameClick(e: React.MouseEvent<HTMLDivElement>) {
    if (step !== 'pick_frame' || framePoints.length >= 4) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = Math.round(e.clientX - rect.left)
    const y = Math.round(e.clientY - rect.top)
    setFramePoints((pts) => [...pts, [x, y]])
  }

  function handleFloorClick(e: React.MouseEvent<HTMLDivElement>) {
    if (step !== 'pick_floor' || floorPoints.length >= 4) return
    const rect = e.currentTarget.getBoundingClientRect()
    const x = Math.round(e.clientX - rect.left)
    const y = Math.round(e.clientY - rect.top)
    setFloorPoints((pts) => [...pts, [x, y]])
  }

  function handleNext() {
    if (step === 'start') {
      setStep('pick_frame')
    } else if (step === 'pick_frame' && framePoints.length === 4) {
      setStep('pick_floor')
    } else if (step === 'pick_floor' && floorPoints.length === 4) {
      setStep('computing')
      const err = simulateReprojError()
      setReprErr(err)
      setStep('review')
    }
  }

  function handleSave() {
    if (reprErr !== null && reprErr < 2) {
      setStep('done')
    }
  }

  function handleReset() {
    setStep('start')
    setFramePoints([])
    setFloorPoints([])
    setReprErr(null)
  }

  const canSave = reprErr !== null && reprErr < 2

  return (
    <div className="space-y-4" aria-label={`Homography calibrator — ${STEP_LABELS[step]}`}>
      <div className="flex items-center gap-2">
        <h2 className="text-[15px] font-medium text-text-primary">Homography Calibration</h2>
        <span className="px-2 py-0.5 rounded bg-surface-sunken text-[12px] text-text-muted">
          {STEP_LABELS[step]}
        </span>
      </div>

      {step === 'start' && (
        <div className="space-y-3">
          <p className="text-[14px] text-text-secondary">
            Calibrate the camera-to-floor homography by picking 4 matching points — first on the
            live frame, then on the floor plan. Reprojection error must be &lt;2 px to save.
          </p>
          <button
            type="button"
            onClick={handleNext}
            className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600"
          >
            Start calibration
          </button>
        </div>
      )}

      {step === 'pick_frame' && (
        <div className="space-y-3">
          <p className="text-[13px] text-text-secondary">
            Click 4 reference points on the frame ({framePoints.length}/4)
          </p>
          <div
            role="img"
            aria-label="Frame point picker"
            onClick={handleFrameClick}
            className="h-40 bg-surface-sunken rounded border border-border flex items-center justify-center cursor-crosshair relative"
          >
            <span className="text-[13px] text-text-muted">Live frame (click to add point)</span>
            {framePoints.map(([x, y], i) => (
              <div
                key={i}
                style={{ position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)' }}
                className="w-3 h-3 bg-brand-500 rounded-full border-2 border-white"
                aria-label={`Frame point ${i + 1}`}
              />
            ))}
          </div>
          <button
            type="button"
            onClick={handleNext}
            disabled={framePoints.length < 4}
            className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Next
          </button>
        </div>
      )}

      {step === 'pick_floor' && (
        <div className="space-y-3">
          <p className="text-[13px] text-text-secondary">
            Click the matching 4 points on the floor plan ({floorPoints.length}/4)
          </p>
          <div
            role="img"
            aria-label="Floor plan point picker"
            onClick={handleFloorClick}
            className="h-40 bg-surface-sunken rounded border border-border flex items-center justify-center cursor-crosshair relative"
          >
            <span className="text-[13px] text-text-muted">Floor plan (click to add point)</span>
            {floorPoints.map(([x, y], i) => (
              <div
                key={i}
                style={{ position: 'absolute', left: x, top: y, transform: 'translate(-50%,-50%)' }}
                className="w-3 h-3 bg-green-500 rounded-full border-2 border-white"
                aria-label={`Floor point ${i + 1}`}
              />
            ))}
          </div>
          <button
            type="button"
            onClick={handleNext}
            disabled={floorPoints.length < 4}
            className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Compute
          </button>
        </div>
      )}

      {step === 'review' && (
        <div className="space-y-4">
          <div
            className={`rounded p-4 border ${
              canSave ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'
            }`}
          >
            <p className="text-[13px] font-medium">
              Reprojection error:{' '}
              <span className={canSave ? 'text-green-800' : 'text-red-700'}>
                {reprErr !== null ? `${reprErr.toFixed(2)} px` : '—'}
              </span>
            </p>
            <p className="text-[12px] text-text-muted mt-1">
              {canSave ? 'Error within tolerance — safe to save.' : 'Error exceeds 2 px limit — recalibrate.'}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleReset}
              className="px-4 py-2 text-[14px] rounded border border-border text-text-secondary hover:text-text-primary"
            >
              Recalibrate
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!canSave}
              aria-disabled={!canSave}
              className="px-4 py-2 text-[14px] rounded bg-brand-500 text-white hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              Save homography
            </button>
          </div>
        </div>
      )}

      {step === 'done' && (
        <div className="bg-green-50 border border-green-200 rounded p-4 space-y-2">
          <p className="text-[14px] font-medium text-green-800">Calibration saved successfully.</p>
          <p className="text-[13px] text-green-700">
            Reprojection error: {reprErr?.toFixed(2)} px
          </p>
          <button
            type="button"
            onClick={handleReset}
            className="px-3 py-1.5 text-[13px] rounded border border-green-300 text-green-800 hover:bg-green-100"
          >
            Recalibrate
          </button>
        </div>
      )}
    </div>
  )
}
