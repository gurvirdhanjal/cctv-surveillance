import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FloatingActionBar, type FloatingAction } from './FloatingActionBar'
import { Eye } from 'lucide-react'

const ACTIONS: FloatingAction[] = [
  { icon: Eye, label: 'Live', onClick: vi.fn() },
  { icon: Eye, label: 'Playback', onClick: vi.fn() },
]

describe('FloatingActionBar', () => {
  it('renders action buttons', () => {
    render(<FloatingActionBar actions={ACTIONS} />)
    expect(screen.getByRole('button', { name: 'Live' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Playback' })).toBeInTheDocument()
  })

  it('calls onClick when action clicked', () => {
    const onClick = vi.fn()
    render(<FloatingActionBar actions={[{ icon: Eye, label: 'Live', onClick }]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Live' }))
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('disables action when disabled=true', () => {
    render(
      <FloatingActionBar
        actions={[{ icon: Eye, label: 'PTZ', onClick: vi.fn(), disabled: true }]}
      />,
    )
    expect(screen.getByRole('button', { name: 'PTZ' })).toBeDisabled()
  })

  it('renders as toolbar role', () => {
    render(<FloatingActionBar actions={ACTIONS} />)
    expect(screen.getByRole('toolbar')).toBeInTheDocument()
  })
})
