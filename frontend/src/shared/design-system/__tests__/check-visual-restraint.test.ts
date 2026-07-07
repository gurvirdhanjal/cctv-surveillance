import { describe, it, expect } from 'vitest'

/** Mirror the gate logic locally so we can test against fixture strings without spawning a process. */

const INVENTED_TOKENS = [
  'surface-elevated',
  'border-subtle',
  'border-muted',
  'text-tertiary',
  'surface-hover',
] as const

const FORBIDDEN_PATTERNS = [
  /ring-brand/,
  /outline-brand/,
  ...INVENTED_TOKENS.map((t) => new RegExp(t)),
] as const

function checkLine(line: string): string[] {
  return FORBIDDEN_PATTERNS.filter((p) => p.test(line)).map((p) => p.toString())
}

describe('Visual restraint gate patterns', () => {
  // ── Invented tokens ────────────────────────────────────────────────
  it('flags surface-elevated (non-existent token)', () => {
    expect(checkLine('className="p-4 surface-elevated shadow"').length).toBeGreaterThan(0)
  })

  it('flags border-subtle (non-existent token)', () => {
    expect(checkLine('className="border-subtle"').length).toBeGreaterThan(0)
  })

  it('flags border-muted (non-existent token)', () => {
    expect(checkLine('className="border-muted"').length).toBeGreaterThan(0)
  })

  it('flags text-tertiary (non-existent token)', () => {
    expect(checkLine('className="text-tertiary"').length).toBeGreaterThan(0)
  })

  it('flags surface-hover (non-existent token)', () => {
    expect(checkLine('className="surface-hover"').length).toBeGreaterThan(0)
  })

  // ── Forbidden color uses ───────────────────────────────────────────
  it('flags ring-brand on a focus ring', () => {
    expect(checkLine('focus:ring-2 focus:ring-brand-500').length).toBeGreaterThan(0)
  })

  it('flags outline-brand on a focus outline', () => {
    expect(checkLine('focus:outline-brand-500').length).toBeGreaterThan(0)
  })

  // ── Legal uses (must NOT flag) ──────────────────────────────────────
  it('does NOT flag --brand-accent on logo/nav element', () => {
    expect(checkLine("style={{ borderLeft: '3px solid var(--brand-accent)' }}")).toHaveLength(0)
  })

  it('does NOT flag action-700 charcoal button', () => {
    expect(checkLine('className="bg-action-700 text-text-inverse"')).toHaveLength(0)
  })

  it('does NOT flag destructive alarm-red severity', () => {
    expect(checkLine('className="bg-[var(--destructive)] text-white"')).toHaveLength(0)
  })

  it('does NOT flag focus-visible:ring-focus-ring (charcoal focus ring)', () => {
    expect(checkLine('focus-visible:ring-2 focus-visible:ring-focus-ring')).toHaveLength(0)
  })

  it('does NOT flag surface-raised (real token)', () => {
    expect(checkLine('className="bg-surface-raised shadow-2"')).toHaveLength(0)
  })
})
