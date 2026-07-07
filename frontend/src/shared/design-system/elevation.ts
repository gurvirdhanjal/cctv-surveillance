/** §C elevation z-index ladder — the only permitted z-index values in the codebase. */
export const Z = {
  bg:       0,
  surface:  0,
  raised:   1,
  selected: 2,
  toolbar:  40,
  modal:    50,
  cmdk:     60,
  toast:    70,
} as const

export type ElevationLayer = keyof typeof Z

/** Shadow tier per elevation layer (maps to --shadow-N CSS var). 0 = none. */
export const ELEVATION_SHADOW: Record<ElevationLayer, 0 | 1 | 2 | 3 | 4> = {
  bg:       0,
  surface:  0,
  raised:   1,
  selected: 2,
  toolbar:  2,
  modal:    3,
  cmdk:     3,
  toast:    4,
} as const
