import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { SHADCN_VAR_MAP, REQUIRED_SHADCN_VARS } from './shadcn-compat'

const cssPath = resolve(__dirname, '../../index.css')
const css = readFileSync(cssPath, 'utf-8')

describe('shadcn compat layer', () => {
  it('every shadcn var maps to a var(--…) reference, not a literal color', () => {
    for (const [varName, value] of Object.entries(SHADCN_VAR_MAP)) {
      // Dark-primary exception: action-600 literal (#334155) for dark visibility
      if (varName === '--primary') continue
      expect(
        value,
        `${varName} must start with var(-- not a literal color`
      ).toMatch(/^var\(--/)
    }
  })

  it('every required shadcn var is declared in index.css compat block', () => {
    for (const varName of REQUIRED_SHADCN_VARS) {
      expect(
        css,
        `${varName} must appear in the shadcn compat layer in index.css`
      ).toContain(varName)
    }
  })

  it('--ring maps to interactive-primary (charcoal focus), not brand-accent (crimson)', () => {
    expect(SHADCN_VAR_MAP['--ring']).toBe('var(--interactive-primary)')
  })

  it('--primary maps to interactive-primary (action-700 charcoal), not brand-accent', () => {
    expect(SHADCN_VAR_MAP['--primary']).toBe('var(--interactive-primary)')
  })

  it('--destructive maps to var(--destructive) (severity-critical only)', () => {
    expect(SHADCN_VAR_MAP['--destructive']).toBe('var(--destructive)')
  })
})
