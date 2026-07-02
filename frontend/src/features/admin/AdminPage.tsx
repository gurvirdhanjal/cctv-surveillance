import { Routes, Route } from 'react-router-dom'
import { AdminLayout } from './AdminLayout'
import { AdminDashboardPage } from './AdminDashboardPage'
import { AdminPersonsPage } from './AdminPersonsPage'
import { AdminCamerasPage } from './AdminCamerasPage'
import { CameraDetailPage } from './CameraDetailPage'
import { ZoneEditorPage } from './ZoneEditorPage'
import { AdminUsersPage } from './AdminUsersPage'
import { MaintenanceCalendarPage } from './MaintenanceCalendarPage'
import { AnomalyDetectorsPage } from './AnomalyDetectorsPage'
import { AlertRoutingPage } from './AlertRoutingPage'
import { ModelManagerPage } from './ModelManagerPage'
import { AuditLogViewerPage } from './AuditLogViewerPage'

export function AdminPage() {
  return (
    <Routes>
      <Route element={<AdminLayout />}>
        <Route index element={<AdminDashboardPage />} />
        <Route path="persons" element={<AdminPersonsPage />} />
        <Route path="cameras" element={<AdminCamerasPage />} />
        <Route path="cameras/:cameraId" element={<CameraDetailPage />} />
        <Route path="zones" element={<ZoneEditorPage />} />
        <Route path="users" element={<AdminUsersPage />} />
        <Route path="maintenance" element={<MaintenanceCalendarPage />} />
        <Route path="anomaly-detectors" element={<AnomalyDetectorsPage />} />
        <Route path="alert-routing" element={<AlertRoutingPage />} />
        <Route path="models" element={<ModelManagerPage />} />
        <Route path="audit" element={<AuditLogViewerPage />} />
      </Route>
    </Routes>
  )
}
