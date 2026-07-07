import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { GridLayoutSelector } from './GridLayoutSelector'
import { useLiveStore } from '../store/liveStore'

const initial = useLiveStore.getState()
beforeEach(() => { useLiveStore.setState(initial, true) })

describe('GridLayoutSelector', () => {
  it('renders four layout options', () => {
    render(<GridLayoutSelector />)
    expect(screen.getAllByRole('radio')).toHaveLength(4)
  })

  it('default layout is 1 (aria-checked on 1×1)', () => {
    render(<GridLayoutSelector />)
    expect(screen.getByRole('radio', { name: '1×1 view' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: '2×2 grid' })).toHaveAttribute('aria-checked', 'false')
  })

  it('clicking 9 sets gridLayout to 9', () => {
    render(<GridLayoutSelector />)
    fireEvent.click(screen.getByRole('radio', { name: '3×3 grid' }))
    expect(useLiveStore.getState().gridLayout).toBe(9)
    expect(screen.getByRole('radio', { name: '3×3 grid' })).toHaveAttribute('aria-checked', 'true')
  })

  it('active option has active styling class', () => {
    useLiveStore.setState({ ...initial, gridLayout: 4 })
    render(<GridLayoutSelector />)
    const btn4 = screen.getByRole('radio', { name: '2×2 grid' })
    expect(btn4.className).toContain('bg-[#232d42]')
  })
})
