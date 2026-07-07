import { useState, useEffect } from 'react'

export type CountdownTier = 'ok' | 'warn' | 'crit'

interface CountdownResult {
  secondsRemaining: number
  fraction: number
  tier: CountdownTier
}

export function useCountdown(deadlineIso: string | null, windowSeconds: number): CountdownResult {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  if (!deadlineIso || windowSeconds <= 0) {
    return { secondsRemaining: 0, fraction: 0, tier: 'crit' }
  }

  const deadlineMs = new Date(deadlineIso).getTime()
  const remainingMs = Math.max(0, deadlineMs - now)
  const secondsRemaining = Math.floor(remainingMs / 1000)
  const fraction = Math.min(1, remainingMs / (windowSeconds * 1000))

  const tier: CountdownTier = fraction > 0.25 ? 'ok' : fraction > 0.1 ? 'warn' : 'crit'

  return { secondsRemaining, fraction, tier }
}
