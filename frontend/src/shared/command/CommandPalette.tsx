import * as React from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
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
import { useWorkspacePrefs } from '@/shared/workspace/useWorkspacePrefs'
import { Icon } from '@/shared/design-system/icons'
import { api } from '@/shared/api/client'
import type { PersonListResponse, CameraResponse, ZoneResponse, AlertResponse } from '@/shared/api/types'
import type { CmdkRecentItem } from '@/shared/workspace/useWorkspacePrefs'

const NAV_ROUTES = [
  { label: 'Live View', icon: Icon.camera, path: '/live', kbd: 'L' },
  { label: 'Analytics', icon: Icon.analytics, path: '/analytics', kbd: 'A' },
  { label: 'Forensic Search', icon: Icon.search, path: '/forensic', kbd: 'F' },
  { label: 'Admin', icon: Icon.settings, path: '/admin', kbd: '' },
]

const ACTION_ITEMS = [
  { label: 'Enrol New Person', icon: Icon.user, path: '/admin/persons?enrol=1' },
  { label: 'Add Camera', icon: Icon.camera, path: '/admin/cameras?add=1' },
  { label: 'Create Zone', icon: Icon.zone, path: '/admin/zones?add=1' },
]

const RECENT_ICON: Record<CmdkRecentItem['type'], React.ComponentType<{ className?: string }>> = {
  camera: Icon.camera,
  person: Icon.user,
  zone: Icon.zone,
  alert: Icon.alert,
  nav: Icon.search,
  action: Icon.settings,
}

export function CommandPalette() {
  const { open, setOpen } = useCommandPaletteStore()
  const navigate = useNavigate()
  const [query, setQuery] = React.useState('')
  const cmdkRecents = useWorkspacePrefs((s) => s.cmdkRecents)
  const pushCmdkRecent = useWorkspacePrefs((s) => s.pushCmdkRecent)

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

  // Reset query when palette closes
  React.useEffect(() => {
    if (!open) setQuery('')
  }, [open])

  const { data: cameras } = useQuery({
    queryKey: ['cmd-cameras'],
    queryFn: () => api.get<CameraResponse[]>('/api/cameras'),
    enabled: open,
    staleTime: 60_000,
  })

  const { data: persons } = useQuery({
    queryKey: ['cmd-persons', query],
    queryFn: () =>
      api.get<PersonListResponse>(`/api/persons?search=${encodeURIComponent(query)}&limit=5`),
    enabled: open && query.length >= 2,
    staleTime: 10_000,
  })

  const { data: zones } = useQuery({
    queryKey: ['cmd-zones'],
    queryFn: () => api.get<ZoneResponse[]>('/api/zones'),
    enabled: open,
    staleTime: 60_000,
  })

  const { data: alerts } = useQuery({
    queryKey: ['cmd-alerts'],
    queryFn: () => api.get<AlertResponse[]>('/api/alerts?state=active&limit=5'),
    enabled: open,
    staleTime: 10_000,
  })

  function run(fn: () => void, recent?: CmdkRecentItem) {
    fn()
    if (recent) pushCmdkRecent(recent)
    setOpen(false)
  }

  const filteredCameras = (cameras ?? [])
    .filter((c) => !query || c.name.toLowerCase().includes(query.toLowerCase()))
    .slice(0, 5)

  const filteredZones = (zones ?? [])
    .filter((z) => !query || z.name.toLowerCase().includes(query.toLowerCase()))
    .slice(0, 5)

  const filteredAlerts = (alerts ?? [])
    .filter((a) => !query || a.alert_type.toLowerCase().includes(query.toLowerCase()))
    .slice(0, 5)

  const showRecents = !query && cmdkRecents.length > 0

  return (
    <CommandDialog open={open} onOpenChange={setOpen}>
      <div className="glass-cmdk z-[60] shadow-4 rounded-xl">
        <CommandInput
          placeholder="Search cameras, persons, pages…"
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          <CommandEmpty>No results found.</CommandEmpty>

          {/* Recent — shown only when query is empty and history non-empty */}
          {showRecents && (
            <>
              <CommandGroup heading="Recent">
                {cmdkRecents.map((item) => {
                  const ItemIcon = RECENT_ICON[item.type]
                  return (
                    <CommandItem
                      key={item.id}
                      value={`recent-${item.id}`}
                      onSelect={() =>
                        run(
                          () => item.path && navigate(item.path),
                          { type: item.type, id: item.id, label: item.label, path: item.path },
                        )
                      }
                    >
                      <ItemIcon className="mr-2 h-4 w-4 text-text-muted" />
                      <span>{item.label}</span>
                    </CommandItem>
                  )
                })}
              </CommandGroup>
              <CommandSeparator />
            </>
          )}

          {/* 1. Cameras */}
          <CommandGroup heading="Cameras">
            {filteredCameras.map((c) => (
              <CommandItem
                key={c.camera_id}
                value={`camera-${c.camera_id}-${c.name}`}
                onSelect={() =>
                  run(
                    () => navigate(`/live?camera=${c.camera_id}`),
                    { type: 'camera', id: String(c.camera_id), label: c.name },
                  )
                }
              >
                <Icon.camera className="mr-2 h-4 w-4 text-text-muted" />
                <span>{c.name}</span>
                <span className="ml-auto text-xs text-text-muted">{c.capability_tier}</span>
              </CommandItem>
            ))}
          </CommandGroup>

          <CommandSeparator />

          {/* 2. Persons */}
          <CommandGroup heading="Persons">
            {(persons?.items ?? []).map((p) => (
              <CommandItem
                key={p.person_id}
                value={`person-${p.person_id}-${p.name}`}
                onSelect={() =>
                  run(
                    () => navigate(`/analytics/persons/${p.person_id}`),
                    { type: 'person', id: String(p.person_id), label: p.name },
                  )
                }
              >
                <Icon.user className="mr-2 h-4 w-4 text-text-muted" />
                <span>{p.name}</span>
                {p.employee_id && (
                  <span className="ml-auto text-xs text-text-muted">{p.employee_id}</span>
                )}
              </CommandItem>
            ))}
          </CommandGroup>

          <CommandSeparator />

          {/* 3. Zones */}
          <CommandGroup heading="Zones">
            {filteredZones.map((z) => (
              <CommandItem
                key={z.zone_id}
                value={`zone-${z.zone_id}-${z.name}`}
                onSelect={() =>
                  run(
                    () => navigate(`/admin/zones?zone=${z.zone_id}`),
                    { type: 'zone', id: String(z.zone_id), label: z.name },
                  )
                }
              >
                <Icon.zone className="mr-2 h-4 w-4 text-text-muted" />
                <span>{z.name}</span>
              </CommandItem>
            ))}
          </CommandGroup>

          <CommandSeparator />

          {/* 4. Alerts */}
          <CommandGroup heading="Alerts">
            {filteredAlerts.map((a) => (
              <CommandItem
                key={a.alert_id}
                value={`alert-${a.alert_id}-${a.alert_type}`}
                onSelect={() =>
                  run(
                    () => navigate(`/live?alert=${a.alert_id}`),
                    { type: 'alert', id: String(a.alert_id), label: a.alert_type },
                  )
                }
              >
                <Icon.alert className="mr-2 h-4 w-4 text-text-muted" />
                <span>{a.alert_type}</span>
                <span className="ml-auto text-xs text-text-muted">{a.severity}</span>
              </CommandItem>
            ))}
          </CommandGroup>

          <CommandSeparator />

          {/* 5. Navigation */}
          <CommandGroup heading="Navigation">
            {NAV_ROUTES.map((r) => (
              <CommandItem
                key={r.path}
                value={r.label}
                onSelect={() =>
                  run(
                    () => navigate(r.path),
                    { type: 'nav', id: r.path, label: r.label, path: r.path },
                  )
                }
              >
                <r.icon className="mr-2 h-4 w-4 text-text-muted" />
                <span>{r.label}</span>
                {r.kbd && <CommandShortcut>{r.kbd}</CommandShortcut>}
              </CommandItem>
            ))}
          </CommandGroup>

          <CommandSeparator />

          {/* 6. Actions */}
          <CommandGroup heading="Actions">
            {ACTION_ITEMS.map((a) => (
              <CommandItem
                key={a.path}
                value={a.label}
                onSelect={() =>
                  run(
                    () => navigate(a.path),
                    { type: 'action', id: a.path, label: a.label, path: a.path },
                  )
                }
              >
                <a.icon className="mr-2 h-4 w-4 text-text-muted" />
                <span>{a.label}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </div>
    </CommandDialog>
  )
}
