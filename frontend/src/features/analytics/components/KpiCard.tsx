interface KpiCardProps {
  label: string
  value: string | number | null
  unit?: string
  loading?: boolean
  error?: boolean
}

export function KpiCard({ label, value, unit, loading = false, error = false }: KpiCardProps) {
  return (
    <div
      className="rounded-lg border border bg-surface-base p-4 shadow-1 hover:shadow-2 transition-shadow duration-fast"
      aria-label={label}
    >
      <p className="text-[12px] font-medium uppercase tracking-wider text-text-muted">{label}</p>
      <div className="mt-2 flex items-baseline gap-1">
        {loading ? (
          <div
            className="h-8 w-24 animate-pulse rounded bg-surface-sunken"
            role="status"
            aria-label="Loading"
          />
        ) : error ? (
          <span className="text-[13px] text-error" role="alert">
            Unavailable
          </span>
        ) : (
          <>
            <span className="text-[28px] font-semibold text-text-primary">
              {value ?? '—'}
            </span>
            {unit && <span className="text-[14px] text-text-muted">{unit}</span>}
          </>
        )}
      </div>
    </div>
  )
}
