import { describe, it, expect } from 'vitest'
import { brand, severity, lightTheme, darkTheme, typeScale, elevation, motion } from './tokens'

describe('severity tokens', () => {
  it('critical is #dc2626', () => {
    expect(severity.critical).toBe('#dc2626')
  })

  it('high is #ea580c', () => {
    expect(severity.high).toBe('#ea580c')
  })

  it('medium is #d97706', () => {
    expect(severity.medium).toBe('#d97706')
  })

  it('low is #65a30d', () => {
    expect(severity.low).toBe('#65a30d')
  })

  it('severity values are theme-invariant (same in light and dark contexts)', () => {
    // Severity must be identical regardless of theme — this is a safety requirement.
    expect(severity.critical).toBe('#dc2626')
    expect(severity.critical).toBe(lightTheme.destructive.base)
    expect(severity.critical).toBe(darkTheme.destructive.base)
  })
})

describe('brand tokens', () => {
  it('has brand-500 as the primary brand color', () => {
    expect(brand[500]).toBe('#2b6cb0')
  })

  it('has brand-950 for dark selected-row (introduced in design system §2.6)', () => {
    expect(brand[950]).toBe('#0a1c33')
    expect(darkTheme.selectedRow).toBe(brand[950])
  })
})

describe('theme shape', () => {
  it('lightTheme has all required token groups', () => {
    expect(lightTheme).toHaveProperty('text')
    expect(lightTheme).toHaveProperty('surface')
    expect(lightTheme).toHaveProperty('border')
    expect(lightTheme).toHaveProperty('focus')
    expect(lightTheme).toHaveProperty('interactive')
    expect(lightTheme).toHaveProperty('destructive')
    expect(lightTheme).toHaveProperty('status')
  })

  it('darkTheme has all required token groups', () => {
    expect(darkTheme).toHaveProperty('text')
    expect(darkTheme).toHaveProperty('surface')
    expect(darkTheme).toHaveProperty('border')
    expect(darkTheme).toHaveProperty('focus')
    expect(darkTheme).toHaveProperty('interactive')
    expect(darkTheme).toHaveProperty('destructive')
    expect(darkTheme).toHaveProperty('status')
  })

  it('light focus ring is brand-500', () => {
    expect(lightTheme.focus.ring).toBe(brand[500])
  })

  it('dark focus ring is brand-300 (higher contrast on dark surface)', () => {
    expect(darkTheme.focus.ring).toBe(brand[300])
  })
})

describe('typeScale', () => {
  it('display-xl is 32px 700 weight', () => {
    expect(typeScale.displayXl.size).toBe(32)
    expect(typeScale.displayXl.weight).toBe(700)
  })

  it('body-md is the default UI size (14px)', () => {
    expect(typeScale.bodyMd.size).toBe(14)
  })

  it('label-xs has wide letter-spacing for uppercase table headers', () => {
    expect(typeScale.labelXs.letterSpacing).toBe('0.06em')
  })
})

describe('elevation', () => {
  it('level 0 is none', () => {
    expect(elevation[0]).toBe('none')
  })

  it('level 3 is the deepest (modals, toasts)', () => {
    expect(elevation[3]).toContain('rgba(0,0,0,0.20)')
  })
})

describe('motion', () => {
  it('base duration is 200ms', () => {
    expect(motion.base).toBe('200ms')
  })
})
