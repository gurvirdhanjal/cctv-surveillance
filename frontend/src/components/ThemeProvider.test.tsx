import { describe, it, expect, beforeEach } from 'vitest'
import { render, act } from '@testing-library/react'
import { ThemeProvider } from './ThemeProvider'
import { useThemeStore } from '@/stores/themeStore'

beforeEach(() => {
  localStorage.clear()
  document.documentElement.setAttribute('data-theme', 'light')
  useThemeStore.setState({ theme: 'light' })
})

describe('ThemeProvider', () => {
  it('sets data-theme=light on mount by default', () => {
    render(<ThemeProvider><div /></ThemeProvider>)
    expect(document.documentElement.getAttribute('data-theme')).toBe('light')
  })

  it('updates data-theme when theme store changes', () => {
    render(<ThemeProvider><div /></ThemeProvider>)
    act(() => {
      useThemeStore.getState().toggleTheme()
    })
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
  })

  it('persists theme to localStorage on toggleTheme', () => {
    render(<ThemeProvider><div /></ThemeProvider>)
    act(() => {
      useThemeStore.getState().toggleTheme()
    })
    expect(localStorage.getItem('vms-theme')).toBe('dark')
  })

  it('applyTheme does NOT write to localStorage (route override)', () => {
    render(<ThemeProvider><div /></ThemeProvider>)
    act(() => {
      useThemeStore.getState().applyTheme('dark')
    })
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark')
    expect(localStorage.getItem('vms-theme')).toBeNull()
  })
})
