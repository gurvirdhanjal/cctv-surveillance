import { Helmet } from 'react-helmet-async'

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
      <div className="p-6 max-w-2xl">
        <h1 className="text-[22px] font-semibold text-text-primary mb-4">Users</h1>
        <div
          role="status"
          aria-label="Users API unavailable"
          className="bg-surface-elevated border border-border-subtle rounded p-6 text-center"
        >
          <p className="text-[15px] font-medium text-text-primary mb-2">
            Users management is not yet available
          </p>
          <p className="text-[13px] text-text-secondary mb-4">
            The Users API (GET/POST/PATCH/DELETE /api/users) needs to be implemented in the
            backend before this page can be used. User accounts can be managed directly in the
            database until then.
          </p>
          <p className="text-[12px] text-text-tertiary font-mono">
            Tracked: plan 2026-06-24-vms-phase4-frontend.md — pre-work P3
          </p>
        </div>
      </div>
    </>
  )
}
