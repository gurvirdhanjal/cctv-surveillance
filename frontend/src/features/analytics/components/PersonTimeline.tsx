interface ZonePresence {
  zone_name: string
  start_hour: number
  end_hour: number
}

interface PersonTimelineProps {
  presences: ZonePresence[]
  hours?: number
}

const ZONE_COLORS = ['#2b6cb0', '#7eb0ff', '#16a34a', '#d97706', '#9333ea', '#dc2626']

export function PersonTimeline({ presences, hours = 24 }: PersonTimelineProps) {
  const zoneNames = [...new Set(presences.map((p) => p.zone_name))]
  const colorMap = new Map(zoneNames.map((name, i) => [name, ZONE_COLORS[i % ZONE_COLORS.length]]))

  return (
    <div aria-label="Person zone timeline" className="overflow-x-auto">
      <div className="relative min-w-[480px]">
        <div className="flex border-b border-border-DEFAULT pb-1">
          <div className="w-20 shrink-0" />
          <div className="flex flex-1">
            {Array.from({ length: hours + 1 }, (_, i) => (
              <div
                key={i}
                className="flex-1 text-center text-[10px] text-text-muted"
              >
                {i % 4 === 0 ? `${i}h` : ''}
              </div>
            ))}
          </div>
        </div>

        {zoneNames.map((zone) => {
          const color = colorMap.get(zone) ?? '#2b6cb0'
          const blocks = presences.filter((p) => p.zone_name === zone)
          return (
            <div key={zone} className="flex items-center py-0.5" data-zone={zone}>
              <div className="w-20 shrink-0 truncate pr-2 text-[12px] text-text-secondary">
                {zone}
              </div>
              <div className="relative flex-1" style={{ height: 16 }}>
                {blocks.map((block, i) => {
                  const left = (block.start_hour / hours) * 100
                  const width = ((block.end_hour - block.start_hour) / hours) * 100
                  return (
                    <div
                      key={i}
                      className="absolute rounded-sm"
                      style={{
                        left: `${left}%`,
                        width: `${width}%`,
                        height: '100%',
                        backgroundColor: color,
                        opacity: 0.8,
                      }}
                      aria-label={`${zone} ${block.start_hour}h–${block.end_hour}h`}
                    />
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>

      <div className="mt-2 flex flex-wrap gap-2">
        {zoneNames.map((zone) => (
          <div key={zone} className="flex items-center gap-1">
            <div className="h-3 w-3 rounded-sm" style={{ backgroundColor: colorMap.get(zone) }} />
            <span className="text-[11px] text-text-secondary">{zone}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
