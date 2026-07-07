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
  it('has brand-500 as the light-theme brass primary', () => {
    expect(brand[500]).toBe('#a8752c')
  })

  it('has brand-950 as the darkest brass surface tint', () => {
    expect(brand[950]).toBe('#2a2013')
  })

  it('dark selectedRow is action charcoal (not brand-950)', () => {
    expect(darkTheme.selectedRow).toBe('#1e293b')
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

  it('light focus ring is action charcoal (matches --focus-ring CSS var)', () => {
    expect(lightTheme.focus.ring).toBe('#1e293b')
  })

  it('dark focus ring is slate-400 for contrast on dark surfaces', () => {
    expect(darkTheme.focus.ring).toBe('#94a3b8')
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
