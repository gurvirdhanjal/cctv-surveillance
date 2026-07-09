import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { LoginPage } from '@/features/auth/LoginPage'
import { NotFoundPage } from '@/features/errors/NotFoundPage'
import { ForbiddenPage } from '@/features/errors/ForbiddenPage'
import { RoleGuard } from './RoleGuard'
import { WorkspaceShell } from '@/shared/workspace/WorkspaceShell'
import { LoadingThreeDotsJumping } from '@/shared/design-system/components/LoadingThreeDotsJumping'

// Code-split top-level pages — loaded only when the route is first visited
const GuardView = lazy(() =>
  import('@/features/guard/GuardView').then((m) => ({ default: m.GuardView })),
)
const LivePage = lazy(() =>
  import('@/features/live/LivePage').then((m) => ({ default: m.LivePage })),
)
const FocusedCameraPage = lazy(() =>
  import('@/features/live/FocusedCameraPage').then((m) => ({ default: m.FocusedCameraPage })),
)
const FollowPersonPage = lazy(() =>
  import('@/features/live/FollowPersonPage').then((m) => ({ default: m.FollowPersonPage })),
)

// Analytics chunk — Recharts isolated here
const AnalyticsLayout = lazy(() =>
  import('@/features/analytics/AnalyticsLayout').then((m) => ({ default: m.AnalyticsLayout })),
)
const AnalyticsDashboardPage = lazy(() =>
  import('@/features/analytics/AnalyticsDashboardPage').then((m) => ({
    default: m.AnalyticsDashboardPage,
  })),
)
const TimelinePage = lazy(() =>
  import('@/features/analytics/TimelinePage').then((m) => ({ default: m.TimelinePage })),
)
const HeatmapPage = lazy(() =>
  import('@/features/analytics/HeatmapPage').then((m) => ({ default: m.HeatmapPage })),
)
const PersonProfilePage = lazy(() =>
  import('@/features/analytics/PersonProfilePage').then((m) => ({
    default: m.PersonProfilePage,
  })),
)

const ForensicSearchPage = lazy(() =>
  import('@/features/forensic/ForensicSearchPage').then((m) => ({
    default: m.ForensicSearchPage,
  })),
)

const AdminPage = lazy(() =>
  import('@/features/admin/AdminPage').then((m) => ({ default: m.AdminPage })),
)

/** Full-screen loader used while lazy chunks are fetching. */
function PageFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-surface-sunken">
      <LoadingThreeDotsJumping size="lg" />
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
        <Route
          path="/live"
          element={
            <RoleGuard allow={['guard', 'manager', 'admin']}>
              <WorkspaceShell workspaceId="operator">
                <LivePage />
              </WorkspaceShell>
            </RoleGuard>
          }
        />
        <Route
          path="/live/cameras/:cameraId"
          element={
            <RoleGuard allow={['guard', 'manager', 'admin']}>
              <FocusedCameraPage />
            </RoleGuard>
          }
        />
        <Route
          path="/live/follow/:trackId"
          element={
            <RoleGuard allow={['guard', 'manager', 'admin']}>
              <FollowPersonPage />
            </RoleGuard>
          }
        />

        {/* Manager and above — analytics nested routes */}
        <Route
          path="/analytics"
          element={
            <RoleGuard allow={['manager', 'admin']}>
              <WorkspaceShell workspaceId="analytics">
                <AnalyticsLayout />
              </WorkspaceShell>
            </RoleGuard>
          }
        >
          <Route index element={<AnalyticsDashboardPage />} />
          <Route path="timeline" element={<TimelinePage />} />
          <Route path="heatmap" element={<HeatmapPage />} />
          <Route path="persons/:id" element={<PersonProfilePage />} />
        </Route>

        <Route
          path="/forensic"
          element={
            <RoleGuard allow={['manager', 'admin']}>
              <WorkspaceShell workspaceId="investigation">
                <ForensicSearchPage />
              </WorkspaceShell>
            </RoleGuard>
          }
        />

        {/* Admin only */}
        <Route
          path="/admin/*"
          element={
            <RoleGuard allow={['admin']}>
              <WorkspaceShell workspaceId="administration">
                <AdminPage />
              </WorkspaceShell>
            </RoleGuard>
          }
        />
      </Routes>
    </Suspense>
  )
}
