import { useState, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { PersonResponse } from '@/shared/api/types'
import { useLiveStore } from '../store/liveStore'
import { HeadCountBanner } from './HeadCountBanner'

export function TopBar() {
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const searchInputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  const alerts = useLiveStore((s) => s.alerts)
  const activeAlertCount = alerts.filter((a) => a.state === 'OPEN').length

  // Cmd+K / Ctrl+K opens search
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setSearchOpen(true)
      }
      if (e.key === 'Escape') {
        setSearchOpen(false)
        setSearchQuery('')
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [])

  // Auto-focus input when dialog opens
  useEffect(() => {
    if (searchOpen) searchInputRef.current?.focus()
  }, [searchOpen])

  const { data: searchResults } = useQuery({
    queryKey: ['persons', 'search', searchQuery],
    queryFn: () => api.get<PersonResponse[]>(`/api/persons/search?q=${encodeURIComponent(searchQuery)}`),
    enabled: searchOpen && searchQuery.trim().length >= 2,
    staleTime: 30_000,
  })

  function handlePersonSelect(person: PersonResponse) {
    navigate(`/analytics/persons/${person.person_id}`)
    setSearchOpen(false)
    setSearchQuery('')
  }

  return (
    <>
      <header className="flex h-14 flex-shrink-0 items-center gap-4 border-b border-border bg-surface-raised px-4">
        <Link
          to="/live"
          className="font-display text-[18px] font-bold text-brand-500 hover:text-brand-700"
          aria-label="VMS — home"
        >
          VMS
        </Link>

        <button
          type="button"
          className="flex items-center gap-2 rounded-md border border-border px-3 py-1.5 text-[13px] text-text-muted hover:border-border-strong"
          onClick={() => setSearchOpen(true)}
          aria-label="Search persons"
        >
          <span>Search</span>
          <kbd className="rounded bg-surface-sunken px-1 py-0.5 text-[10px]">Ctrl K</kbd>
        </button>

        <div className="flex-1" />

        <HeadCountBanner />

        {activeAlertCount > 0 && (
          <Link
            to="/live"
            className="flex items-center gap-1 rounded-md bg-severity-high/10 px-2.5 py-1 text-[13px] font-semibold text-severity-high"
            aria-label={`${activeAlertCount} active alerts`}
          >
            {activeAlertCount} alerts
          </Link>
        )}
      </header>

      {/* Search modal */}
      {searchOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Person search"
          className="fixed inset-0 z-50 flex items-start justify-center pt-20"
        >
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/40"
            aria-hidden="true"
            onClick={() => {
              setSearchOpen(false)
              setSearchQuery('')
            }}
          />
          <div className="relative z-10 w-full max-w-lg overflow-hidden rounded-xl bg-surface-raised shadow-3">
            <input
              ref={searchInputRef}
              type="text"
              className="w-full border-b border-border bg-transparent px-4 py-3 text-[15px] text-text-primary outline-none placeholder:text-text-muted"
              placeholder="Search by name or employee ID…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              aria-label="Search persons"
            />
            {searchResults && searchResults.length > 0 && (
              <ul>
                {searchResults.map((person) => (
                  <li key={person.person_id}>
                    <button
                      type="button"
                      className="flex w-full items-center gap-3 px-4 py-2.5 text-[14px] text-text-primary hover:bg-surface-sunken"
                      onClick={() => handlePersonSelect(person)}
                    >
                      <span className="font-medium">{person.name}</span>
                      <span className="text-text-muted">{person.employee_id}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {searchResults?.length === 0 && searchQuery.trim().length >= 2 && (
              <p className="px-4 py-3 text-[14px] text-text-muted">No results</p>
            )}
          </div>
        </div>
      )}
    </>
  )
}
