import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useCountdown } from './useCountdown'

describe('useCountdown', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('initializes with fraction near 1 for far-future deadline', () => {
    const deadline = new Date(Date.now() + 100_000).toISOString()
    const { result } = renderHook(() => useCountdown(deadline, 100))
    expect(result.current.fraction).toBeCloseTo(1, 1)
    expect(result.current.tier).toBe('ok')
  })

  it('fraction decreases after timer ticks', () => {
    const deadline = new Date(Date.now() + 100_000).toISOString()
    const { result } = renderHook(() => useCountdown(deadline, 100))
    const before = result.current.fraction
    act(() => vi.advanceTimersByTime(10_000))
    expect(result.current.fraction).toBeLessThan(before)
  })

  it('tier is ok when fraction > 0.25', () => {
    const deadline = new Date(Date.now() + 50_000).toISOString()
    const { result } = renderHook(() => useCountdown(deadline, 100))
    expect(result.current.tier).toBe('ok')
  })

  it('tier flips to warn when fraction ≤ 0.25', () => {
    const deadline = new Date(Date.now() + 24_000).toISOString()
    const { result } = renderHook(() => useCountdown(deadline, 100))
    expect(result.current.tier).toBe('warn')
  })

  it('tier is crit when fraction ≤ 0.10', () => {
    const deadline = new Date(Date.now() + 9_000).toISOString()
    const { result } = renderHook(() => useCountdown(deadline, 100))
    expect(result.current.tier).toBe('crit')
  })

  it('clamps at 0 when past deadline', () => {
    const deadline = new Date(Date.now() - 5_000).toISOString()
    const { result } = renderHook(() => useCountdown(deadline, 100))
    expect(result.current.secondsRemaining).toBe(0)
    expect(result.current.fraction).toBe(0)
    expect(result.current.tier).toBe('crit')
  })

  it('returns crit for null deadline', () => {
    const { result } = renderHook(() => useCountdown(null, 100))
    expect(result.current.tier).toBe('crit')
    expect(result.current.secondsRemaining).toBe(0)
  })
})
