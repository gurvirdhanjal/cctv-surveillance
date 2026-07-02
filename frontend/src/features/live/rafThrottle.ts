import { useLiveStore } from './store/liveStore'
import type { PersonLocation } from './types'

const pending = new Map<string, PersonLocation>()
let rafId = 0

export function queuePersonLocation(loc: PersonLocation): void {
  pending.set(loc.global_track_id, loc)
  if (!rafId) {
    rafId = requestAnimationFrame(flush)
  }
}

export function flush(): void {
  rafId = 0
  if (pending.size > 0) {
    useLiveStore.getState().applyLocations(Array.from(pending.values()))
    pending.clear()
  }
}

/** Reset internal state — test helper only. */
export function _resetThrottle(): void {
  pending.clear()
  if (rafId) {
    cancelAnimationFrame(rafId)
    rafId = 0
  }
}
