import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { CommandPalette } from './CommandPalette'
import { useCommandPaletteStore } from '@/stores/commandPaletteStore'
import { useWorkspacePrefs } from '@/shared/workspace/useWorkspacePrefs'

vi.mock('@/shared/api/client', () => ({
  api: { get: vi.fn().mockResolvedValue([]) },
}))

// Mock cmdk components to avoid jsdom incompatibilities (ResizeObserver, scrollIntoView)
vi.mock('@/shared/design-system/components/ui/Command', () => ({
  CommandDialog: ({ open, onOpenChange, children }: { open: boolean; onOpenChange: (v: boolean) => void; children: unknown }) =>
    open ? (
      <div role="dialog" aria-modal="true">
        <button data-testid="close-dialog" onClick={() => onOpenChange(false)} aria-label="Close" />
        {children as never}
      </div>
    ) : null,
  CommandInput: ({ value, onValueChange, placeholder }: { value: string; onValueChange: (v: string) => void; placeholder?: string }) => (
    <input
      role="searchbox"
      value={value}
      onChange={(e) => onValueChange(e.target.value)}
      placeholder={placeholder}
    />
  ),
  CommandList: ({ children }: { children: unknown }) => <div>{children as never}</div>,
  CommandEmpty: ({ children }: { children: unknown }) => <div>{children as never}</div>,
  CommandGroup: ({ heading, children }: { heading: string; children: unknown }) => (
    <div data-group={heading}>
      <span>{heading}</span>
      {children as never}
    </div>
  ),
  CommandItem: ({ children, onSelect }: { children: unknown; onSelect: () => void }) => (
    <div role="option" onClick={onSelect}>{children as never}</div>
  ),
  CommandSeparator: () => <hr />,
  CommandShortcut: ({ children }: { children: unknown }) => <kbd>{children as never}</kbd>,
}))

const initialPalette = useCommandPaletteStore.getState()
const initialPrefs = useWorkspacePrefs.getState()

function setup() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <CommandPalette />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  useCommandPaletteStore.setState(initialPalette, true)
  useWorkspacePrefs.setState({ ...initialPrefs, cmdkRecents: [] })
})

describe('CommandPalette', () => {
  it('opens on Ctrl+K', () => {
    setup()
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('renders all 6 group headings when open', () => {
    setup()
    act(() => { useCommandPaletteStore.setState({ open: true }) })
    expect(screen.getByText('Cameras')).toBeInTheDocument()
    expect(screen.getByText('Persons')).toBeInTheDocument()
    expect(screen.getByText('Zones')).toBeInTheDocument()
    expect(screen.getByText('Alerts')).toBeInTheDocument()
    expect(screen.getByText('Navigation')).toBeInTheDocument()
    expect(screen.getByText('Actions')).toBeInTheDocument()
  })

  it('palette wrapper has glass-cmdk class when open', () => {
    const { container } = setup()
    act(() => { useCommandPaletteStore.setState({ open: true }) })
    const glassCmdk = container.querySelector('.glass-cmdk')
    expect(glassCmdk).not.toBeNull()
  })

  it('palette wrapper has z-[60] class when open', () => {
    const { container } = setup()
    act(() => { useCommandPaletteStore.setState({ open: true }) })
    // glass-cmdk div also carries z-[60]; just verify the wrapper exists
    const wrapper = container.querySelector('.glass-cmdk')
    expect(wrapper).not.toBeNull()
    // check class string contains z-[60]
    expect(wrapper?.className).toContain('z-[60]')
  })

  it('shows Recent heading when cmdkRecents is non-empty and query is empty', () => {
    act(() => {
      useWorkspacePrefs.setState({
        ...initialPrefs,
        cmdkRecents: [{ type: 'camera', id: '1', label: 'Gate A', path: '/live' }],
      })
    })
    setup()
    act(() => { useCommandPaletteStore.setState({ open: true }) })
    expect(screen.getByText('Recent')).toBeInTheDocument()
  })

  it('does not show Recent heading when cmdkRecents is empty', () => {
    act(() => { useWorkspacePrefs.setState({ ...initialPrefs, cmdkRecents: [] }) })
    setup()
    act(() => { useCommandPaletteStore.setState({ open: true }) })
    expect(screen.queryByText('Recent')).not.toBeInTheDocument()
  })

  it('pushCmdkRecent function is available in the prefs store', () => {
    setup()
    expect(typeof useWorkspacePrefs.getState().pushCmdkRecent).toBe('function')
  })

  it('dialog is closed when onOpenChange(false) is called', () => {
    setup()
    act(() => { useCommandPaletteStore.setState({ open: true }) })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('close-dialog'))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
