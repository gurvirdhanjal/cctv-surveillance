import { describe, it, expect, vi, afterEach } from 'vitest'
import { EASE, MOTION, reducedMotionSafe } from './motion'

describe('EASE curve (§H)', () => {
  it('is exactly [0.4, 0, 0.2, 1]', () => {
    expect(EASE).toEqual([0.4, 0, 0.2, 1])
  })
})

describe('MOTION presets (§H)', () => {
  it('hover is 0.08s', () => { expect(MOTION.hover.duration).toBe(0.08) })
  it('dropdown is 0.12s', () => { expect(MOTION.dropdown.duration).toBe(0.12) })
  it('popover is 0.15s', () => { expect(MOTION.popover.duration).toBe(0.15) })
  it('modal is 0.18s', () => { expect(MOTION.modal.duration).toBe(0.18) })
  it('sidebar is 0.18s', () => { expect(MOTION.sidebar.duration).toBe(0.18) })
  it('accordion is 0.16s', () => { expect(MOTION.accordion.duration).toBe(0.16) })
  it('page is 0.15s', () => { expect(MOTION.page.duration).toBe(0.15) })
  it('toast is 0.20s', () => { expect(MOTION.toast.duration).toBe(0.20) })

  it('every preset carries the standard EASE curve', () => {
    for (const [name, cfg] of Object.entries(MOTION)) {
      expect(cfg.ease, `${name}.ease`).toEqual(EASE)
    }
  })
})

describe('reducedMotionSafe (§H)', () => {
  afterEach(() => { vi.restoreAllMocks() })

  it('returns the original config when reduced motion is off', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
    } as MediaQueryList)
    expect(reducedMotionSafe(MOTION.modal)).toEqual(MOTION.modal)
  })

  it('collapses to duration:0 when prefers-reduced-motion matches', () => {
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: true,
    } as MediaQueryList)
    const safe = reducedMotionSafe(MOTION.modal)
    expect(safe.duration).toBe(0)
  })
})
