import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const RECENT_CAMERAS_MAX = 10
export const CMDK_RECENTS_MAX = 8

export interface TableLayoutPrefs {
  columnOrder: string[]
  columnSizing: Record<string, number>
  columnPinning: { left: string[]; right: string[] }
  density: 'compact' | 'default' | 'relaxed'
  sorting: Array<{ id: string; desc: boolean }>
}

export interface CmdkRecentItem {
  type: 'camera' | 'person' | 'zone' | 'alert' | 'nav' | 'action'
  id: string
  label: string
  path?: string
}

export type WorkspaceTheme = 'light' | 'dark' | 'system'

export interface WorkspacePrefs {
  version: number
  tableLayouts: Record<string, TableLayoutPrefs>
  workspaceThemes: Record<string, WorkspaceTheme>
  sidebarOpen: boolean
  favoriteCameraIds: number[]
  defaultGridLayout: string
  recentCameraIds: number[]
  pinnedAlertIds: string[]
  treeExpansion: Record<string, boolean>
  treeOrder: Record<string, number[]>
  cmdkRecents: CmdkRecentItem[]
  panelLayouts: Record<string, number[]>
}

interface WorkspacePrefsActions {
  pushRecentCamera: (id: number) => void
  pushCmdkRecent: (item: CmdkRecentItem) => void
  setTableLayout: (tableId: string, layout: Partial<TableLayoutPrefs>) => void
  setWorkspaceTheme: (workspaceId: string, theme: WorkspaceTheme) => void
  setSidebarOpen: (open: boolean) => void
  setTreeExpansion: (nodeId: string, expanded: boolean) => void
  setTreeOrder: (zoneId: string, cameraIds: number[]) => void
  setPanelLayout: (workspaceId: string, sizes: number[]) => void
  toggleFavoriteCamera: (id: number) => void
}

const DEFAULT_STATE: WorkspacePrefs = {
  version: 1,
  tableLayouts: {},
  workspaceThemes: {},
  sidebarOpen: true,
  favoriteCameraIds: [],
  defaultGridLayout: '3x3',
  recentCameraIds: [],
  pinnedAlertIds: [],
  treeExpansion: {},
  treeOrder: {},
  cmdkRecents: [],
  panelLayouts: {},
}

function migrate(persisted: unknown, fromVersion: number): WorkspacePrefs {
  // Coerce any unknown version to the current shape
  if (fromVersion < 1 || typeof persisted !== 'object' || persisted === null) {
    return { ...DEFAULT_STATE }
  }
  return { ...DEFAULT_STATE, ...(persisted as Partial<WorkspacePrefs>) }
}

export const useWorkspacePrefs = create<WorkspacePrefs & WorkspacePrefsActions>()(
  persist(
    (set) => ({
      ...DEFAULT_STATE,

      pushRecentCamera: (id) =>
        set((s) => {
          const next = [id, ...s.recentCameraIds.filter((x) => x !== id)]
          return { recentCameraIds: next.slice(0, RECENT_CAMERAS_MAX) }
        }),

      pushCmdkRecent: (item) =>
        set((s) => {
          const next = [item, ...s.cmdkRecents.filter((x) => x.id !== item.id)]
          return { cmdkRecents: next.slice(0, CMDK_RECENTS_MAX) }
        }),

      setTableLayout: (tableId, layout) =>
        set((s) => ({
          tableLayouts: {
            ...s.tableLayouts,
            [tableId]: { ...s.tableLayouts[tableId], ...layout } as TableLayoutPrefs,
          },
        })),

      setWorkspaceTheme: (workspaceId, theme) =>
        set((s) => ({
          workspaceThemes: { ...s.workspaceThemes, [workspaceId]: theme },
        })),

      setSidebarOpen: (open) => set({ sidebarOpen: open }),

      setTreeExpansion: (nodeId, expanded) =>
        set((s) => ({
          treeExpansion: { ...s.treeExpansion, [nodeId]: expanded },
        })),

      setTreeOrder: (zoneId, cameraIds) =>
        set((s) => ({
          treeOrder: { ...s.treeOrder, [zoneId]: cameraIds },
        })),

      setPanelLayout: (workspaceId, sizes) =>
        set((s) => ({
          panelLayouts: { ...s.panelLayouts, [workspaceId]: sizes },
        })),

      toggleFavoriteCamera: (id) =>
        set((s) => ({
          favoriteCameraIds: s.favoriteCameraIds.includes(id)
            ? s.favoriteCameraIds.filter((x) => x !== id)
            : [...s.favoriteCameraIds, id],
        })),
    }),
    {
      name: 'vms.workspace',
      version: 1,
      migrate: (persisted, version) => migrate(persisted, version),
    },
  ),
)
