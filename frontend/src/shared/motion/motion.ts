export const EASE = [0.4, 0, 0.2, 1] as const

const t = (duration: number) => ({ duration, ease: EASE as unknown as number[] })

/** §H canonical motion presets — import these instead of hard-coding durations. */
export const MOTION = {
  /** 80ms — icon swap, tooltip fade */
  hover:     t(0.08),
  /** 120ms — dropdown open/close */
  dropdown:  t(0.12),
  /** 150ms — popover, command palette */
  popover:   t(0.15),
  /** 180ms — modal enter/exit */
  modal:     t(0.18),
  /** 180ms — sidebar slide */
  sidebar:   t(0.18),
  /** 160ms — accordion expand */
  accordion: t(0.16),
  /** 150ms — page transition */
  page:      t(0.15),
  /** 200ms — toast enter */
  toast:     t(0.20),
} as const

type MotionConfig = { duration: number; ease: readonly number[] }

/** Returns the config unchanged, or `{ duration: 0 }` when prefers-reduced-motion is set. */
export function reducedMotionSafe(cfg: MotionConfig): MotionConfig {
  if (typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
    return { duration: 0, ease: cfg.ease }
  }
  return cfg
}
