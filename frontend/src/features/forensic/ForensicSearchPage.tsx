import { Helmet } from 'react-helmet-async'
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { ForensicClip } from '@/shared/api/types'
import { NotImplementedError } from '@/shared/api/errors'
import { ClipResultCard } from './components/ClipResultCard'
import { ClipDrawer } from './components/ClipDrawer'

interface SearchFilters {
  query: string
  time_from: string
  time_to: string
}

const DEFAULT_FILTERS: SearchFilters = { query: '', time_from: '', time_to: '' }

export function ForensicSearchPage() {
  const [filters, setFilters] = useState<SearchFilters>(DEFAULT_FILTERS)
  const [submitted, setSubmitted] = useState(false)
  const [selectedClip, setSelectedClip] = useState<ForensicClip | null>(null)

  const { data, isLoading, error } = useQuery({
    queryKey: ['forensic-search', filters],
    queryFn: () =>
      api.get<ForensicClip[]>(
        `/api/forensic/search?q=${encodeURIComponent(filters.query)}` +
          (filters.time_from ? `&from=${filters.time_from}` : '') +
          (filters.time_to ? `&to=${filters.time_to}` : ''),
      ),
    enabled: submitted,
    retry: false,
    staleTime: 30_000,
  })

  const isClipBlocked = error instanceof NotImplementedError

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    setSubmitted(true)
  }

  return (
    <>
      <Helmet title="Forensic Search" />
      <div className="min-h-screen space-y-6 bg-surface-base p-6" data-theme="light">
        <h1 className="text-[20px] font-semibold text-text-primary">Forensic Search</h1>

        {isClipBlocked && (
          <div
            role="status"
            aria-label="Search unavailable"
            className="rounded-md border border-warning/50 bg-warning/10 px-4 py-3 text-[13px] text-text-secondary"
          >
            Forensic search unavailable — CLIP text encoder not yet deployed. Search is disabled
            until the text encoder is configured (<code>VMS_CLIP_MODEL</code>).
          </div>
        )}

        <form
          onSubmit={handleSearch}
          aria-label="Forensic search form"
          className="space-y-4"
        >
          <div className="flex gap-2">
            <input
              type="text"
              value={filters.query}
              onChange={(e) => setFilters((f) => ({ ...f, query: e.target.value }))}
              placeholder="Describe what you're looking for…"
              disabled={isClipBlocked}
              aria-label="Search query"
              className="flex-1 rounded-md border border bg-surface-base px-3 py-2 text-[14px] placeholder:text-text-muted focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)] disabled:cursor-not-allowed disabled:opacity-50"
            />
            <button
              type="submit"
              disabled={isClipBlocked || !filters.query.trim()}
              className="rounded-md bg-action-700 px-4 py-2 text-[13px] font-medium text-white hover:bg-action-800 disabled:opacity-40"
            >
              Search
            </button>
          </div>

          <div className="flex flex-wrap gap-3" aria-label="Search filters">
            <input
              type="datetime-local"
              value={filters.time_from}
              onChange={(e) => setFilters((f) => ({ ...f, time_from: e.target.value }))}
              disabled={isClipBlocked}
              aria-label="From date"
              className="rounded-md border border px-2 py-1 text-[13px] disabled:opacity-50"
            />
            <input
              type="datetime-local"
              value={filters.time_to}
              onChange={(e) => setFilters((f) => ({ ...f, time_to: e.target.value }))}
              disabled={isClipBlocked}
              aria-label="To date"
              className="rounded-md border border px-2 py-1 text-[13px] disabled:opacity-50"
            />
          </div>
        </form>

        {isLoading && (
          <div role="status" aria-label="Searching" className="text-[14px] text-text-muted">
            Searching…
          </div>
        )}
        {!isLoading && data && data.length === 0 && (
          <p className="text-[14px] text-text-muted">
            No results found. Try a different description.
          </p>
        )}
        {!isLoading && data && data.length > 0 && (
          <div className="grid grid-cols-3 gap-4" aria-label="Search results">
            {data.map((clip) => (
              <ClipResultCard
                key={clip.global_track_id}
                clip={clip}
                onClick={() => setSelectedClip(clip)}
              />
            ))}
          </div>
        )}
      </div>

      {selectedClip && (
        <ClipDrawer clip={selectedClip} onClose={() => setSelectedClip(null)} />
      )}
    </>
  )
}
