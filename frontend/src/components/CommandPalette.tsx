import * as React from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Camera, User, Settings, BarChart2, Search, Shield, Calendar, Bell } from 'lucide-react'
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
  CommandSeparator,
  CommandShortcut,
} from '@/shared/design-system/components/ui/Command'
import { useCommandPaletteStore } from '@/stores/commandPaletteStore'
import { api } from '@/shared/api/client'
import type { PersonListResponse, CameraResponse } from '@/shared/api/types'

export function CommandPalette() {
  const { open, setOpen } = useCommandPaletteStore()
  const navigate = useNavigate()
  const [query, setQuery] = React.useState('')

  // Global Cmd+K / Ctrl+K listener
  React.useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setOpen(!open)
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [open, setOpen])

  const { data: persons } = useQuery({
    queryKey: ['cmd-persons', query],
    queryFn: () =>
      api.get<PersonListResponse>(`/api/persons?search=${encodeURIComponent(query)}&limit=5`),
    enabled: open && query.length >= 2,
    staleTime: 10_000,
  })

  const { data: cameras } = useQuery({
    queryKey: ['cmd-cameras'],
    queryFn: () => api.get<CameraResponse[]>('/api/cameras'),
    enabled: open,
    staleTime: 60_000,
  })

  function run(fn: () => void) {
    fn()
    setOpen(false)
    setQuery('')
  }

  const adminRoutes = [
    { label: 'Cameras', icon: Camera, path: '/admin/cameras', kbd: '' },
    { label: 'Persons', icon: User, path: '/admin/persons', kbd: '' },
    { label: 'Users', icon: Shield, path: '/admin/users', kbd: '' },
    { label: 'Anomaly Detectors', icon: Settings, path: '/admin/anomaly-detectors', kbd: '' },
    { label: 'Alert Routing', icon: Bell, path: '/admin/alert-routing', kbd: '' },
    { label: 'Maintenance Calendar', icon: Calendar, path: '/admin/maintenance', kbd: '' },
    { label: 'Audit Log', icon: Search, path: '/admin/audit-log', kbd: '' },
  ]

  const topRoutes = [
    { label: 'Live View', icon: Camera, path: '/live', kbd: 'L' },
    { label: 'Analytics', icon: BarChart2, path: '/analytics', kbd: 'A' },
    { label: 'Forensic Search', icon: Search, path: '/forensic', kbd: 'F' },
    { label: 'Guard View', icon: Shield, path: '/guard', kbd: 'G' },
  ]

  const filteredCameras = (cameras ?? []).filter(
    (c) =>
      !query ||
      c.name.toLowerCase().includes(query.toLowerCase())
  ).slice(0, 5)

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <CommandInput
        placeholder="Search people, cameras, pages..."
        value={query}
        onValueChange={setQuery}
      />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>

        {/* Person search results */}
        {persons && persons.items.length > 0 && (
          <CommandGroup heading="People">
            {persons.items.map((p) => (
              <CommandItem
                key={p.person_id}
                value={`person-${p.person_id}-${p.name}`}
                onSelect={() => run(() => navigate(`/analytics/persons/${p.person_id}`))}
              >
                <User className="mr-2 h-4 w-4 text-text-muted" />
                <span>{p.name}</span>
                {p.employee_id && (
                  <span className="ml-2 text-xs text-text-muted">{p.employee_id}</span>
                )}
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        {/* Camera navigation */}
        {filteredCameras.length > 0 && (
          <CommandGroup heading="Cameras">
            {filteredCameras.map((c) => (
              <CommandItem
                key={c.camera_id}
                value={`camera-${c.camera_id}-${c.name}`}
                onSelect={() => run(() => navigate(`/live/cameras/${c.camera_id}`))}
              >
                <Camera className="mr-2 h-4 w-4 text-text-muted" />
                <span>{c.name}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}

        <CommandSeparator />

        {/* Top-level navigation */}
        <CommandGroup heading="Navigate">
          {topRoutes.map((r) => (
            <CommandItem
              key={r.path}
              value={r.label}
              onSelect={() => run(() => navigate(r.path))}
            >
              <r.icon className="mr-2 h-4 w-4 text-text-muted" />
              <span>{r.label}</span>
              {r.kbd && <CommandShortcut>{r.kbd}</CommandShortcut>}
            </CommandItem>
          ))}
        </CommandGroup>

        <CommandSeparator />

        {/* Admin shortcuts */}
        <CommandGroup heading="Admin">
          {adminRoutes.map((r) => (
            <CommandItem
              key={r.path}
              value={r.label}
              onSelect={() => run(() => navigate(r.path))}
            >
              <r.icon className="mr-2 h-4 w-4 text-text-muted" />
              <span>{r.label}</span>
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  )
}
