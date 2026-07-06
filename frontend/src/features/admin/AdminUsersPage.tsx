import { Helmet } from 'react-helmet-async'
import { UserCog } from 'lucide-react'
import { EmptyState } from './components/EmptyState'

/**
 * Users CRUD is blocked on the P3 pre-work sub-task: implement
 * POST/GET/PATCH/DELETE /api/users in the backend (User model exists
 * in vms/db/models.py but no route file has been created yet).
 * Track: plan 2026-06-24-vms-phase4-frontend.md — P3 sub-task.
 */
export function AdminUsersPage() {
  return (
    <>
      <Helmet title="Users — Admin" />
      <div className="p-6">
        <h1 className="mb-5 text-[22px] font-bold text-text-primary">Users</h1>
        <div role="status" aria-label="Users API unavailable">
          <EmptyState
            icon={UserCog}
            title="Users management coming soon"
            description="The /api/users backend endpoint is required before this page can be used. Tracked: plan 2026-06-24-vms-phase4-frontend.md — pre-work P3."
          />
        </div>
      </div>
    </>
  )
}
