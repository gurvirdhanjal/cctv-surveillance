import { Helmet } from 'react-helmet-async'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { PersonProfile, AlertResponse } from '@/shared/api/types'
import { DwellChart } from './components/DwellChart'
import { PersonTimeline } from './components/PersonTimeline'

export function PersonProfilePage() {
  const { id } = useParams<{ id: string }>()
  const personId = id ? parseInt(id, 10) : NaN

  const {
    data: person,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ['person', personId],
    queryFn: () => api.get<PersonProfile>(`/api/persons/${personId}`),
    enabled: !isNaN(personId),
    staleTime: 60_000,
  })

  const { data: alertsResponse } = useQuery({
    queryKey: ['person-alerts', personId],
    queryFn: () =>
      api.get<{ items: AlertResponse[] }>(`/api/alerts?person_id=${personId}&limit=10`),
    enabled: !isNaN(personId),
    staleTime: 30_000,
  })

  if (isLoading) {
    return (
      <div role="status" aria-label="Loading profile" className="space-y-4">
        <div className="h-20 w-full animate-pulse rounded bg-surface-sunken" />
        <div className="h-40 w-full animate-pulse rounded bg-surface-sunken" />
      </div>
    )
  }

  if (isError || !person) {
    return (
      <div role="alert" className="rounded-md bg-error/10 px-4 py-3 text-[14px] text-error">
        Could not load person profile.
      </div>
    )
  }

  return (
    <>
      <Helmet title={person.name} />
      <div className="space-y-6">
        <div className="flex items-center gap-4">
          {person.thumbnail_url ? (
            <img
              src={person.thumbnail_url}
              alt={person.name}
              className="h-16 w-16 rounded-full object-cover"
            />
          ) : (
            <div className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-100 text-[20px] font-semibold text-brand-700">
              {person.name.charAt(0).toUpperCase()}
            </div>
          )}
          <div>
            <h1 className="text-[20px] font-semibold text-text-primary">{person.name}</h1>
            <p className="text-[14px] text-text-secondary">
              {person.employee_id}
              {person.department ? ` · ${person.department}` : ''}
            </p>
            {person.last_seen_at && (
              <p className="text-[12px] text-text-muted">
                Last seen: {new Date(person.last_seen_at).toLocaleString()}
              </p>
            )}
          </div>
          <div className="ml-auto">
            <Link
              to={`/analytics?open_scrubber=person_${personId}`}
              className="rounded-md border border-border-DEFAULT px-3 py-1.5 text-[13px] text-text-secondary hover:bg-surface-sunken"
            >
              Open in timeline scrubber
            </Link>
          </div>
        </div>

        <section aria-label="Zone dwell times">
          <h2 className="mb-3 text-[15px] font-medium text-text-primary">Today&apos;s zone dwell</h2>
          <DwellChart data={[]} />
        </section>

        <section aria-label="24-hour journey">
          <h2 className="mb-3 text-[15px] font-medium text-text-primary">24-hour journey</h2>
          <PersonTimeline presences={[]} />
        </section>

        {alertsResponse?.items && alertsResponse.items.length > 0 && (
          <section aria-label="Recent alerts">
            <h2 className="mb-3 text-[15px] font-medium text-text-primary">Recent alerts</h2>
            <ul className="space-y-2">
              {alertsResponse.items.map((alert) => (
                <li
                  key={alert.alert_id}
                  className="flex items-center gap-3 rounded-md border border-border-DEFAULT px-3 py-2 text-[13px]"
                >
                  <span className="text-text-secondary">{alert.alert_type}</span>
                  <span className="text-text-muted">
                    {new Date(alert.triggered_at).toLocaleString()}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </>
  )
}
