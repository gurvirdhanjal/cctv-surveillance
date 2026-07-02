import { useState } from 'react'

type PlaybackSpeed = 0.5 | 1 | 2 | 5 | 10

const SPEEDS: PlaybackSpeed[] = [0.5, 1, 2, 5, 10]

interface ScrubberState {
  playing: boolean
  speed: PlaybackSpeed
  positionPct: number
}

interface TimeScrubberProps {
  disabled?: boolean
}

export function TimeScrubber({ disabled = false }: TimeScrubberProps) {
  const [state, setState] = useState<ScrubberState>({
    playing: false,
    speed: 1,
    positionPct: 0,
  })

  function togglePlay() {
    setState((s) => ({ ...s, playing: !s.playing }))
  }

  function setSpeed(speed: PlaybackSpeed) {
    setState((s) => ({ ...s, speed }))
  }

  function stepForward() {
    setState((s) => ({ ...s, positionPct: Math.min(100, s.positionPct + 1), playing: false }))
  }

  function stepBack() {
    setState((s) => ({ ...s, positionPct: Math.max(0, s.positionPct - 1), playing: false }))
  }

  return (
    <div
      aria-label="Timeline scrubber"
      className="space-y-4 rounded-lg border border bg-surface-base p-4"
    >
      {disabled && (
        <div role="status" className="rounded-md bg-surface-sunken px-4 py-3 text-[13px] text-text-secondary">
          Timeline data pending (Phase 5) — scrubber controls are shown for reference.
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <button
          aria-label="Step back"
          onClick={stepBack}
          disabled={disabled}
          className="rounded-md border border px-2 py-1 text-[13px] hover:bg-surface-sunken disabled:opacity-40"
        >
          &laquo;
        </button>
        <button
          aria-label={state.playing ? 'Pause' : 'Play'}
          onClick={togglePlay}
          disabled={disabled}
          className="rounded-md border border px-3 py-1 text-[13px] hover:bg-surface-sunken disabled:opacity-40"
        >
          {state.playing ? 'Pause' : 'Play'}
        </button>
        <button
          aria-label="Step forward"
          onClick={stepForward}
          disabled={disabled}
          className="rounded-md border border px-2 py-1 text-[13px] hover:bg-surface-sunken disabled:opacity-40"
        >
          &raquo;
        </button>

        <span className="mx-1 text-[13px] text-text-muted">Speed:</span>
        {SPEEDS.map((s) => (
          <button
            key={s}
            aria-label={`${s}× speed`}
            aria-pressed={state.speed === s}
            onClick={() => setSpeed(s)}
            disabled={disabled}
            className={[
              'rounded-md px-2 py-1 text-[12px] transition-colors disabled:opacity-40',
              state.speed === s
                ? 'bg-brand-500 text-text-inverse'
                : 'border border hover:bg-surface-sunken',
            ].join(' ')}
          >
            {s}&times;
          </button>
        ))}
      </div>

      <input
        type="range"
        min={0}
        max={100}
        value={state.positionPct}
        onChange={(e) => setState((s) => ({ ...s, positionPct: Number(e.target.value) }))}
        disabled={disabled}
        aria-label="Scrubber position"
        className="w-full disabled:opacity-40"
      />
    </div>
  )
}
