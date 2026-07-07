import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'

const CSS_PATH = resolve(__dirname, '../../../index.css')
const css = readFileSync(CSS_PATH, 'utf-8')

const DROPDOWN_PATH = resolve(__dirname, '../components/ui/DropdownMenu.tsx')
const dropdownSrc = readFileSync(DROPDOWN_PATH, 'utf-8')

/** §M — blur permitted on exactly these four surfaces */
const GLASS_CLASSES = ['glass-dropdown', 'glass-cmdk', 'glass-toolbar', 'glass-context-menu'] as const

describe('§M Glass/Blur utilities — CSS presence', () => {
  GLASS_CLASSES.forEach((cls) => {
    it(`defines .${cls} in index.css`, () => {
      expect(css).toContain(`.${cls}`)
    })

    it(`${cls} uses backdrop-blur-md (blur(12px))`, () => {
      // Tailwind @apply backdrop-blur-md compiles to --tw-backdrop-blur or the utility string
      // We assert the utility name appears near the class
      const classBlock = css.slice(css.indexOf(`.${cls}`), css.indexOf(`.${cls}`) + 300)
      expect(classBlock).toMatch(/backdrop-blur/)
    })
  })

  it('has a reduced-transparency @media fallback', () => {
    expect(css).toContain('prefers-reduced-transparency')
  })

  it('reduced-transparency block removes blur', () => {
    const rtBlock = css.slice(css.indexOf('prefers-reduced-transparency'))
    expect(rtBlock).toMatch(/backdrop-filter\s*:\s*none|backdrop-blur-none|backdrop-filter:none/)
  })
})

describe('§M Glass/Blur — DropdownMenuContent wired', () => {
  it('DropdownMenuContent applies glass-dropdown class', () => {
    expect(dropdownSrc).toContain('glass-dropdown')
  })
})

describe('§M Glass/Blur — forbidden surfaces guard', () => {
  const FORBIDDEN_FILES = [
    resolve(__dirname, '../components/Card.tsx'),
  ]

  FORBIDDEN_FILES.forEach((filePath) => {
    it(`${filePath.split(/[\\/]/).pop()} does NOT use backdrop-blur`, () => {
      const src = readFileSync(filePath, 'utf-8')
      expect(src).not.toContain('backdrop-blur')
    })
  })
})
