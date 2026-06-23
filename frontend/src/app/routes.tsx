import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { LoginPage } from '@/features/auth/LoginPage'
import { NotFoundPage } from '@/features/errors/NotFoundPage'
import { ForbiddenPage } from '@/features/errors/ForbiddenPage'
import { RoleGuard } from './RoleGuard'

// Code-split top-level pages — loaded only when the route is first visited
const GuardView = lazy(() =>
  import('@/features/guard/GuardView').then((m) => ({ default: m.GuardView })),
)
const AnalyticsPage = lazy(() =>
  import('@/features/analytics/AnalyticsPage').then((m) => ({ default: m.AnalyticsPage })),
)
const ForensicPage = lazy(() =>
  import('@/features/forensic/ForensicPage').then((m) => ({ default: m.ForensicPage })),
)
const AdminPage = lazy(() =>
  import('@/features/admin/AdminPage').then((m) => ({ default: m.AdminPage })),
)

/** Full-screen loading shimmer used while lazy chunks are fetching. */
function PageFallback() {
  return (
    <div
      role="status"
      aria-label="Loading page"
      className="flex min-h-screen items-center justify-center bg-surface-sunken"
    >
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-200 border-t-brand-500" />
    </div>
  )
}

export function AppRoutes() {
  return (
    <Suspense fallback={<PageFallback />}>
      <Routes>
        {/* Public */}
        <Route path="/login" element={<LoginPage />} />
        <Route path="/403" element={<ForbiddenPage />} />
        <Route path="*" element={<NotFoundPage />} />

        {/* Guard role and above */}
        <Route
          path="/"
          element={
            <RoleGuard allow={['guard', 'manager', 'admin']}>
              <GuardView />
            </RoleGuard>
          }
        />
        <Route
          path="/guard"
          element={
            <RoleGuard allow={['guard', 'manager', 'admin']}>
              <GuardView />
            </RoleGuard>
          }
        />

        {/* Manager and above */}
        <Route
          path="/analytics"
          element={
            <RoleGuard allow={['manager', 'admin']}>
              <AnalyticsPage />
            </RoleGuard>
          }
        />
        <Route
          path="/forensic"
          element={
            <RoleGuard allow={['manager', 'admin']}>
              <ForensicPage />
            </RoleGuard>
          }
        />

        {/* Admin only */}
        <Route
          path="/admin/*"
          element={
            <RoleGuard allow={['admin']}>
              <AdminPage />
            </RoleGuard>
          }
        />
      </Routes>
    </Suspense>
  )
}
