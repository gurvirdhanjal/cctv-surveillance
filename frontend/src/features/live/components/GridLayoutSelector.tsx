import { Square, Grid2x2, Grid3x3, LayoutGrid } from 'lucide-react'
import { cn } from '@/shared/utils/cn'
import { useLiveStore } from '../store/liveStore'

const OPTIONS = [
  { value: 1 as const, Icon: Square, label: '1×1 view' },
  { value: 4 as const, Icon: Grid2x2, label: '2×2 grid' },
  { value: 9 as const, Icon: Grid3x3, label: '3×3 grid' },
  { value: 16 as const, Icon: LayoutGrid, label: '4×4 wall' },
]

export function GridLayoutSelector() {
  const gridLayout = useLiveStore((s) => s.gridLayout)
  const setGridLayout = useLiveStore((s) => s.setGridLayout)

  return (
    <div
      role="radiogroup"
      aria-label="Grid layout"
      className="inline-flex rounded-[10px] border border-[#1e293b] bg-[#111827] p-0.5"
    >
      {OPTIONS.map(({ value, Icon, label }) => {
        const active = gridLayout === value
        return (
          <button
            key={value}
            type="button"
            role="radio"
            aria-checked={active}
            aria-label={label}
            onClick={() => setGridLayout(value)}
            className={cn(
              'flex h-7 w-7 items-center justify-center rounded-[8px] transition-colors',
              active
                ? 'bg-[#232d42] text-slate-100'
                : 'text-slate-400 hover:bg-[#1a2234]'
            )}
          >
            <Icon className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        )
      })}
    </div>
  )
}
