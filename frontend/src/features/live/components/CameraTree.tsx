import { useState, useEffect, useCallback, useMemo } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronRight } from 'lucide-react'
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable'
import { Virtuoso } from 'react-virtuoso'
import { useLiveStore } from '../store/liveStore'
import { useWorkspacePrefs } from '@/shared/workspace/useWorkspacePrefs'
import { CameraTile } from './CameraTile'
import { GridLayoutSelector } from './GridLayoutSelector'
import type { CameraState } from '../types'
import { cn } from '@/shared/utils/cn'

const PAGE_SIZE = 12

// ── Hierarchy grouping ──────────────────────────────────────────────────────

interface ZoneGroup {
  zoneKey: string
  label: string
  cameras: CameraState[]
}
interface FloorGroup {
  floorKey: string
  label: string
  zones: ZoneGroup[]
}
interface BuildingGroup {
  buildingKey: string
  label: string
  floors: FloorGroup[]
}
interface SiteGroup {
  siteKey: string
  label: string
  buildings: BuildingGroup[]
}

function buildHierarchy(cameras: CameraState[]): SiteGroup[] {
  const sites = new Map<string, Map<string, Map<string, Map<string, CameraState[]>>>>()

  for (const cam of cameras) {
    const site = cam.site_name ?? 'Default Site'
    const building = cam.building_name ?? 'Default Building'
    const floor = cam.floor_name ?? 'Ground Floor'
    const zone = 'Unzoned'

    if (!sites.has(site)) sites.set(site, new Map())
    const buildings = sites.get(site)!
    if (!buildings.has(building)) buildings.set(building, new Map())
    const floors = buildings.get(building)!
    if (!floors.has(floor)) floors.set(floor, new Map())
    const zones = floors.get(floor)!
    if (!zones.has(zone)) zones.set(zone, [])
    zones.get(zone)!.push(cam)
  }

  return Array.from(sites.entries()).map(([siteLabel, buildings]) => ({
    siteKey: siteLabel,
    label: siteLabel,
    buildings: Array.from(buildings.entries()).map(([buildingLabel, floors]) => ({
      buildingKey: `${siteLabel}/${buildingLabel}`,
      label: buildingLabel,
      floors: Array.from(floors.entries()).map(([floorLabel, zones]) => ({
        floorKey: `${siteLabel}/${buildingLabel}/${floorLabel}`,
        label: floorLabel,
        zones: Array.from(zones.entries()).map(([zoneLabel, cams]) => ({
          zoneKey: `${siteLabel}/${buildingLabel}/${floorLabel}/${zoneLabel}`,
          label: zoneLabel,
          cameras: cams,
        })),
      })),
    })),
  }))
}

function getAllAncestorKeys(hierarchy: SiteGroup[], cameraId: number): Set<string> {
  const keys = new Set<string>()
  for (const site of hierarchy) {
    for (const building of site.buildings) {
      for (const floor of building.floors) {
        for (const zone of floor.zones) {
          if (zone.cameras.some((c) => c.camera_id === cameraId)) {
            keys.add(site.siteKey)
            keys.add(building.buildingKey)
            keys.add(floor.floorKey)
            keys.add(zone.zoneKey)
          }
        }
      }
    }
  }
  return keys
}

// ── Tree node component ─────────────────────────────────────────────────────

interface TreeNodeProps {
  nodeKey: string
  label: string
  level: number
  children: React.ReactNode
}

function TreeNode({ nodeKey, label, level, children }: TreeNodeProps) {
  const expanded = useWorkspacePrefs((s) => s.treeExpansion[nodeKey] ?? true)
  const setExpansion = useWorkspacePrefs((s) => s.setTreeExpansion)

  return (
    <div>
      <button
        type="button"
        className={cn(
          'flex w-full items-center gap-1.5 rounded px-2 py-1 text-left text-[12px] font-medium text-slate-300 hover:bg-white/5',
          level === 0 && 'text-slate-200 font-semibold',
        )}
        style={{ paddingLeft: `${8 + level * 12}px` }}
        aria-expanded={expanded}
        onClick={() => setExpansion(nodeKey, !expanded)}
      >
        <motion.span
          animate={{ rotate: expanded ? 90 : 0 }}
          transition={{ duration: 0.16 }}
          className="flex-shrink-0"
        >
          <ChevronRight className="h-3 w-3 text-slate-500" />
        </motion.span>
        {label}
      </button>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.16, ease: [0.4, 0, 0.2, 1] }}
            style={{ overflow: 'hidden' }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Sortable camera row (dnd-kit) ───────────────────────────────────────────

interface SortableCameraRowProps {
  camera: CameraState
  isFocused: boolean
  isAlarming: boolean
  onSelect: () => void
  level: number
}

function SortableCameraRow({ camera, isFocused, isAlarming, onSelect, level }: SortableCameraRowProps) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useSortable({
    id: camera.camera_id,
  })

  return (
    <div
      ref={setNodeRef}
      {...attributes}
      {...listeners}
      style={{
        paddingLeft: `${8 + level * 12}px`,
        opacity: isDragging ? 0.5 : 1,
        transform: transform ? `translateY(${transform.y}px)` : undefined,
      }}
      className="py-0.5"
    >
      <CameraTile
        camera={camera}
        isFocused={isFocused}
        isAlarming={isAlarming}
        onSelect={onSelect}
      />
    </div>
  )
}

// ── Flat row type for Virtuoso ──────────────────────────────────────────────

type FlatRow =
  | { type: 'site'; nodeKey: string; label: string; level: number }
  | { type: 'building'; nodeKey: string; label: string; level: number }
  | { type: 'floor'; nodeKey: string; label: string; level: number }
  | { type: 'zone'; nodeKey: string; label: string; level: number; cameras: CameraState[] }

// ── Main component ──────────────────────────────────────────────────────────

export function CameraTree() {
  const cameras = useLiveStore((s) => s.cameras)
  const focusedCameraId = useLiveStore((s) => s.focusedCameraId)
  const alerts = useLiveStore((s) => s.alerts)
  const setFocusedCamera = useLiveStore((s) => s.setFocusedCamera)
  const treeOrder = useWorkspacePrefs((s) => s.treeOrder)
  const setTreeOrder = useWorkspacePrefs((s) => s.setTreeOrder)
  const treeExpansion = useWorkspacePrefs((s) => s.treeExpansion)

  const [search, setSearch] = useState('')
  const [page, setPage] = useState(0)

  const alarmingCameraIds = useMemo(() => {
    const ids = new Set<number>()
    for (const a of alerts) {
      if (a.state === 'OPEN' && a.camera_id !== null) ids.add(a.camera_id)
    }
    return ids
  }, [alerts])

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim()
    return q ? cameras.filter((c) => c.name.toLowerCase().includes(q)) : cameras
  }, [cameras, search])

  const hierarchy = useMemo(() => buildHierarchy(filtered), [filtered])

  // Keys whose ancestors must remain visible during search
  const searchAncestorKeys = useMemo(() => {
    if (!search) return new Set<string>()
    const keys = new Set<string>()
    for (const cam of filtered) {
      const ancestorKeys = getAllAncestorKeys(hierarchy, cam.camera_id)
      ancestorKeys.forEach((k) => keys.add(k))
    }
    return keys
  }, [search, filtered, hierarchy])

  const useVirtuoso = cameras.length > 200

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))

  useEffect(() => {
    if (focusedCameraId === null) return
    const idx = filtered.findIndex((c) => c.camera_id === focusedCameraId)
    if (idx >= 0) setPage(Math.floor(idx / PAGE_SIZE))
  }, [focusedCameraId, filtered])

  useEffect(() => setPage(0), [search])

  const goToFocusedPage = useCallback(() => {
    if (focusedCameraId === null) return
    const idx = filtered.findIndex((c) => c.camera_id === focusedCameraId)
    if (idx >= 0) setPage(Math.floor(idx / PAGE_SIZE))
  }, [filtered, focusedCameraId])

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') goToFocusedPage()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [goToFocusedPage])

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  function handleDragEnd(zoneKey: string, zoneCameras: CameraState[], event: DragEndEvent) {
    const { active, over } = event
    if (!over || active.id === over.id) return
    const ids = zoneCameras.map((c) => c.camera_id)
    const fromIdx = ids.indexOf(active.id as number)
    const toIdx = ids.indexOf(over.id as number)
    if (fromIdx === -1 || toIdx === -1) return
    const reordered = [...ids]
    reordered.splice(fromIdx, 1)
    reordered.splice(toIdx, 0, active.id as number)
    setTreeOrder(zoneKey, reordered)
  }

  function getSortedCameras(zoneKey: string, zoneCameras: CameraState[]): CameraState[] {
    const order = treeOrder[zoneKey]
    if (!order) return zoneCameras
    const byId = new Map(zoneCameras.map((c) => [c.camera_id, c]))
    return order.flatMap((id) => (byId.has(id) ? [byId.get(id)!] : []))
      .concat(zoneCameras.filter((c) => !order.includes(c.camera_id)))
  }

  function isNodeVisible(nodeKey: string): boolean {
    if (!search) return true
    return searchAncestorKeys.has(nodeKey)
  }

  // Virtuoso flat-list rendering for large trees
  if (useVirtuoso) {
    const rows: FlatRow[] = []
    for (const site of hierarchy) {
      rows.push({ type: 'site', nodeKey: site.siteKey, label: site.label, level: 0 })
      const siteExpanded = treeExpansion[site.siteKey] ?? true
      if (!siteExpanded) continue
      for (const building of site.buildings) {
        rows.push({ type: 'building', nodeKey: building.buildingKey, label: building.label, level: 1 })
        const bldExpanded = treeExpansion[building.buildingKey] ?? true
        if (!bldExpanded) continue
        for (const floor of building.floors) {
          rows.push({ type: 'floor', nodeKey: floor.floorKey, label: floor.label, level: 2 })
          const floorExpanded = treeExpansion[floor.floorKey] ?? true
          if (!floorExpanded) continue
          for (const zone of floor.zones) {
            rows.push({ type: 'zone', nodeKey: zone.zoneKey, label: zone.label, level: 3, cameras: zone.cameras })
          }
        }
      }
    }

    return (
      <div className="flex h-full flex-col overflow-hidden">
        <div className="flex flex-shrink-0 items-center gap-2 border-b border-[#1e293b] p-2">
          <input
            type="search"
            placeholder="Search cameras…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-9 min-w-0 flex-1 rounded-[10px] border border-[#1e293b] bg-[#1a2234] px-2.5 text-[13px] text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-[var(--focus-ring)]"
            aria-label="Search cameras"
          />
          <GridLayoutSelector />
        </div>
        <Virtuoso
          data={rows}
          itemContent={(_index, row) => {
            if (row.type === 'zone') {
              const sorted = getSortedCameras(row.nodeKey, row.cameras)
              return (
                <div style={{ paddingLeft: `${8 + row.level * 12}px` }}>
                  {sorted.map((cam) => (
                    <CameraTile
                      key={cam.camera_id}
                      camera={cam}
                      isFocused={cam.camera_id === focusedCameraId}
                      isAlarming={alarmingCameraIds.has(cam.camera_id)}
                      onSelect={() => setFocusedCamera(cam.camera_id)}
                    />
                  ))}
                </div>
              )
            }
            return (
              <div
                className="flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 text-[12px] font-medium text-slate-300 hover:bg-white/5"
                style={{ paddingLeft: `${8 + row.level * 12}px` }}
              >
                <ChevronRight className="h-3 w-3 text-slate-500" />
                {row.label}
              </div>
            )
          }}
        />
      </div>
    )
  }

  // Standard paginated tree
  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex flex-shrink-0 items-center gap-2 border-b border-[#1e293b] p-2">
        <input
          type="search"
          placeholder="Search cameras…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-9 min-w-0 flex-1 rounded-[10px] border border-[#1e293b] bg-[#1a2234] px-2.5 text-[13px] text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-[var(--focus-ring)]"
          aria-label="Search cameras"
        />
        <GridLayoutSelector />
      </div>

      <div className="flex-1 overflow-y-auto p-2">
        {hierarchy.length === 0 ? (
          <p className="py-8 text-center text-[13px] text-slate-500">No cameras found</p>
        ) : search ? (
          // Flat list during search (ancestors shown as labels above)
          <>
            {hierarchy.map((site) => (
              <div key={site.siteKey} style={{ display: isNodeVisible(site.siteKey) ? undefined : 'none' }}>
                <div className="px-2 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                  {site.label}
                </div>
                <div className="grid grid-cols-2 gap-1.5">
                  {filtered.map((cam) => (
                    <CameraTile
                      key={cam.camera_id}
                      camera={cam}
                      isFocused={cam.camera_id === focusedCameraId}
                      isAlarming={alarmingCameraIds.has(cam.camera_id)}
                      onSelect={() => setFocusedCamera(cam.camera_id)}
                    />
                  ))}
                </div>
              </div>
            ))}
          </>
        ) : (
          // Hierarchical tree
          <>
            {hierarchy.map((site) => (
              <TreeNode key={site.siteKey} nodeKey={site.siteKey} label={site.label} level={0}>
                {site.buildings.map((building) => (
                  <TreeNode key={building.buildingKey} nodeKey={building.buildingKey} label={building.label} level={1}>
                    {building.floors.map((floor) => (
                      <TreeNode key={floor.floorKey} nodeKey={floor.floorKey} label={floor.label} level={2}>
                        {floor.zones.map((zone) => {
                          const sorted = getSortedCameras(zone.zoneKey, zone.cameras)
                          const pageCams = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)
                          return (
                            <DndContext
                              key={zone.zoneKey}
                              sensors={sensors}
                              collisionDetection={closestCenter}
                              onDragEnd={(e) => handleDragEnd(zone.zoneKey, zone.cameras, e)}
                            >
                              <SortableContext
                                items={sorted.map((c) => c.camera_id)}
                                strategy={verticalListSortingStrategy}
                              >
                                <div className="grid grid-cols-2 gap-1.5 py-1" style={{ paddingLeft: `${8 + 3 * 12}px` }}>
                                  {pageCams.map((cam) => (
                                    <SortableCameraRow
                                      key={cam.camera_id}
                                      camera={cam}
                                      isFocused={cam.camera_id === focusedCameraId}
                                      isAlarming={alarmingCameraIds.has(cam.camera_id)}
                                      onSelect={() => setFocusedCamera(cam.camera_id)}
                                      level={0}
                                    />
                                  ))}
                                </div>
                              </SortableContext>
                            </DndContext>
                          )
                        })}
                      </TreeNode>
                    ))}
                  </TreeNode>
                ))}
              </TreeNode>
            ))}
          </>
        )}
      </div>

      {/* Pager (for non-search mode with more than PAGE_SIZE cameras) */}
      {!search && totalPages > 1 && (
        <div className="flex flex-shrink-0 items-center justify-center gap-2 border-t border-[#1e293b] py-1.5">
          <button
            type="button"
            className="rounded px-2 py-1 text-[12px] text-slate-400 disabled:opacity-30 hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            aria-label="Previous page"
          >
            Prev
          </button>
          <span className="font-mono text-[13px] text-slate-400">
            {page + 1} / {totalPages}
          </span>
          <button
            type="button"
            className="rounded px-2 py-1 text-[12px] text-slate-400 disabled:opacity-30 hover:text-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--focus-ring)]"
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page === totalPages - 1}
            aria-label="Next page"
          >
            Next
          </button>
        </div>
      )}
    </div>
  )
}
