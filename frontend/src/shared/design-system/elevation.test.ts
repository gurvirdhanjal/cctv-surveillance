import { describe, it, expect } from 'vitest'
import { Z, ELEVATION_SHADOW } from './elevation'

describe('Z index ladder (§C)', () => {
  it('bg is 0', () => { expect(Z.bg).toBe(0) })
  it('surface is 0', () => { expect(Z.surface).toBe(0) })
  it('raised is 1', () => { expect(Z.raised).toBe(1) })
  it('selected is 2', () => { expect(Z.selected).toBe(2) })
  it('toolbar is 40', () => { expect(Z.toolbar).toBe(40) })
  it('modal is 50', () => { expect(Z.modal).toBe(50) })
  it('cmdk is 60', () => { expect(Z.cmdk).toBe(60) })
  it('toast is 70', () => { expect(Z.toast).toBe(70) })

  it('toast > cmdk > modal > toolbar (correct stacking order)', () => {
    expect(Z.toast).toBeGreaterThan(Z.cmdk)
    expect(Z.cmdk).toBeGreaterThan(Z.modal)
    expect(Z.modal).toBeGreaterThan(Z.toolbar)
  })
})

describe('ELEVATION_SHADOW mapping (§C)', () => {
  it('bg has no shadow (0)', () => { expect(ELEVATION_SHADOW.bg).toBe(0) })
  it('surface has no shadow (0)', () => { expect(ELEVATION_SHADOW.surface).toBe(0) })
  it('raised has shadow-1', () => { expect(ELEVATION_SHADOW.raised).toBe(1) })
  it('selected has shadow-2', () => { expect(ELEVATION_SHADOW.selected).toBe(2) })
  it('toolbar has shadow-2', () => { expect(ELEVATION_SHADOW.toolbar).toBe(2) })
  it('modal has shadow-3', () => { expect(ELEVATION_SHADOW.modal).toBe(3) })
  it('cmdk has shadow-3', () => { expect(ELEVATION_SHADOW.cmdk).toBe(3) })
  it('toast has shadow-4', () => { expect(ELEVATION_SHADOW.toast).toBe(4) })
})
