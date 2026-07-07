import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Icon, type IconName } from './icons'

const REQUIRED_NAMES: IconName[] = [
  'server', 'camera', 'recording', 'disconnected', 'analytics', 'storage',
  'health', 'ai', 'map', 'playback', 'export', 'search', 'filter', 'add',
  'edit', 'delete', 'bookmark', 'ptz', 'live', 'settings', 'user', 'users',
  'zone', 'alert', 'audit', 'calendar', 'sync', 'calibrate', 'close',
  'chevron-up', 'chevron-down', 'chevron-left', 'chevron-right',
  'grid', 'list', 'pin',
]

describe('icon registry (§B)', () => {
  it('exports a component for each of the 36 required semantic names', () => {
    for (const name of REQUIRED_NAMES) {
      expect(Icon[name], `Icon.${name} should exist`).toBeTruthy()
    }
  })

  it('no two registry keys share the same lucide component (one-to-one)', () => {
    const seen = new Set<unknown>()
    for (const [key, component] of Object.entries(Icon)) {
      expect(seen.has(component), `duplicate component for key "${key}"`).toBe(false)
      seen.add(component)
    }
  })

  it('renders an svg element', () => {
    const CameraIcon = Icon.camera
    const { container } = render(<CameraIcon />)
    expect(container.querySelector('svg')).toBeTruthy()
  })

  it('has at least 36 entries in the registry', () => {
    expect(Object.keys(Icon).length).toBeGreaterThanOrEqual(36)
  })
})
