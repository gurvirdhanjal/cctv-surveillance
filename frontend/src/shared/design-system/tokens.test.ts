import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { brand, severity, lightTheme, darkTheme, typeScale, elevation, motion, radius, durations, interactionStates } from './tokens'

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

  it('level 3 uses §G slate-900 shadow', () => {
    expect(elevation[3]).toContain('rgba(15,23,42,0.14)')
  })
})

describe('motion', () => {
  it('base duration is 200ms', () => {
    expect(motion.base).toBe('200ms')
  })
})

describe('radius tokens (§G)', () => {
  it('xs is 2px', () => { expect(radius.xs).toBe('2px') })
  it('sm is 4px', () => { expect(radius.sm).toBe('4px') })
  it('md is 6px', () => { expect(radius.md).toBe('6px') })
  it('lg is 8px', () => { expect(radius.lg).toBe('8px') })
  it('xl is 12px', () => { expect(radius.xl).toBe('12px') })
  it('2xl is 16px', () => { expect(radius['2xl']).toBe('16px') })
  it('full is 9999px', () => { expect(radius.full).toBe('9999px') })
})

describe('duration tokens (§G)', () => {
  it('fast is 80ms', () => { expect(durations.fast).toBe('80ms') })
  it('normal is 120ms', () => { expect(durations.normal).toBe('120ms') })
  it('slow is 180ms', () => { expect(durations.slow).toBe('180ms') })
  it('xslow is 300ms', () => { expect(durations.xslow).toBe('300ms') })
})

describe('elevation level 4 (§G shadow-4)', () => {
  it('level 4 exists as the deepest shadow', () => {
    expect(elevation[4]).toBeTruthy()
  })
})

describe('interaction state tokens (§G)', () => {
  it('focusRing references --state-focus-ring CSS var', () => {
    expect(interactionStates.focusRing).toBe('var(--state-focus-ring)')
    expect(interactionStates.focusRing).not.toContain('brand-accent')
  })
  it('selection references --state-selection CSS var', () => {
    expect(interactionStates.selection).toBe('var(--state-selection)')
  })
  it('hoverOverlay and pressedOverlay are rgba values', () => {
    expect(interactionStates.hoverOverlay).toContain('rgba')
    expect(interactionStates.pressedOverlay).toContain('rgba')
  })
})

describe('§G CSS custom properties present in index.css', () => {
  const css = readFileSync(resolve(__dirname, '../../index.css'), 'utf8')

  it('--radius-xs is defined', () => { expect(css).toContain('--radius-xs') })
  it('--radius-sm is defined', () => { expect(css).toContain('--radius-sm') })
  it('--dur-fast is defined', () => { expect(css).toContain('--dur-fast') })
  it('--dur-normal is defined', () => { expect(css).toContain('--dur-normal') })
  it('--dur-slow is defined', () => { expect(css).toContain('--dur-slow') })
  it('--dur-xslow is defined', () => { expect(css).toContain('--dur-xslow') })
  it('--shadow-4 is defined in light theme', () => { expect(css).toContain('--shadow-4') })
  it('--state-focus-ring is defined', () => { expect(css).toContain('--state-focus-ring') })
  it('--state-selection is defined', () => { expect(css).toContain('--state-selection') })
  it('--state-hover-overlay is defined', () => { expect(css).toContain('--state-hover-overlay') })
  it('--state-pressed-overlay is defined', () => { expect(css).toContain('--state-pressed-overlay') })
  it('light shadow-1 uses slate-900 rgba (§G supersedes old values)', () => {
    expect(css).toContain('rgba(15, 23, 42, 0.06)')
  })
  it('--state-focus-ring does not use --brand-accent', () => {
    const focusRingLine = css.split('\n').find(l => l.includes('--state-focus-ring'))
    expect(focusRingLine).toBeTruthy()
    expect(focusRingLine).not.toContain('brand-accent')
  })
})
