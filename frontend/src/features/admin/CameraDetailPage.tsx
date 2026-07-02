import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Helmet } from 'react-helmet-async'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/shared/api/client'
import type { CameraResponse } from '@/shared/api/types'
import { HardwareTab } from './camera-tabs/HardwareTab'
import { OverridesTab } from './camera-tabs/OverridesTab'
import { HomographyCalibrator } from './camera-tabs/HomographyCalibrator'

type TabId = 'profile' | 'hardware' | 'overrides' | 'topology' | 'config'

const TABS: { id: TabId; label: string }[] = [
  { id: 'profile', label: 'Profile' },
  { id: 'hardware', label: 'Hardware' },
  { id: 'overrides', label: 'Overrides' },
  { id: 'topology', label: 'Topology' },
  { id: 'config', label: 'Resolved Config' },
]

export function CameraDetailPage() {
  const { cameraId } = useParams<{ cameraId: string }>()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<TabId>('profile')

  const camId = Number(cameraId)

  const { data: camera, isLoading } = useQuery<CameraResponse>({
    queryKey: ['admin', 'cameras', camId],
    queryFn: () => api.get(`/api/cameras/${camId}`),
    enabled: !isNaN(camId),
  })

  if (isLoading) {
    return (
      <div className="p-6">
        <p role="status" aria-label="Loading camera">
          Loading…
        </p>
      </div>
    )
  }

  if (!camera) {
    return (
      <div className="p-6">
        <p role="alert" className="text-red-600 text-[14px]">
          Camera not found.
        </p>
      </div>
    )
  }

  return (
    <>
      <Helmet title={`${camera.name} — Admin`} />
      <div className="p-6">
        <div className="flex items-center gap-3 mb-6">
          <button
            type="button"
            onClick={() => navigate('/admin/cameras')}
            aria-label="Back to cameras"
            className="text-text-muted hover:text-text-primary text-[20px] leading-none"
          >
            ←
          </button>
          <h1 className="text-[22px] font-semibold text-text-primary">{camera.name}</h1>
          <span className="text-[12px] font-mono text-text-muted">ID {camId}</span>
        </div>

        <div
          role="tablist"
          aria-label="Camera configuration tabs"
          className="flex gap-1 border-b border-border mb-6"
        >
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              role="tab"
              id={`tab-${id}`}
              aria-selected={activeTab === id}
              aria-controls={`tabpanel-${id}`}
              onClick={() => setActiveTab(id)}
              className={`px-4 py-2 text-[14px] border-b-2 transition-colors -mb-px ${
                activeTab === id
                  ? 'border-brand-500 text-brand-600 font-medium'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <div
          role="tabpanel"
          id={`tabpanel-${activeTab}`}
          aria-labelledby={`tab-${activeTab}`}
        >
          {activeTab === 'profile' && (
            <div className="space-y-4 text-[14px]">
              <dl className="grid grid-cols-2 gap-x-6 gap-y-3">
                <div>
                  <dt className="text-[12px] text-text-muted mb-0.5">Capability Tier</dt>
                  <dd className="font-medium text-text-primary">{camera.capability_tier}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-text-muted mb-0.5">Shutter Type</dt>
                  <dd className="font-medium text-text-primary">{camera.shutter_type}</dd>
                </div>
                <div>
                  <dt className="text-[12px] text-text-muted mb-0.5">Status</dt>
                  <dd className="font-medium text-text-primary">
                    {camera.is_active ? 'Active' : 'Inactive'}
                  </dd>
                </div>
                <div>
                  <dt className="text-[12px] text-text-muted mb-0.5">Profiled At</dt>
                  <dd className="font-medium text-text-primary font-mono">
                    {camera.profiled_at ?? '—'}
                  </dd>
                </div>
              </dl>
            </div>
          )}

          {activeTab === 'hardware' && <HardwareTab cameraId={camId} />}

          {activeTab === 'overrides' && <OverridesTab cameraId={camId} />}

          {activeTab === 'topology' && (
            <div className="space-y-4">
              <HomographyCalibrator cameraId={camId} />
            </div>
          )}

          {activeTab === 'config' && <ResolvedConfigTab cameraId={camId} />}
        </div>
      </div>
    </>
  )
}

function ResolvedConfigTab({ cameraId }: { cameraId: number }) {
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'cameras', cameraId, 'resolved-config'],
    queryFn: () => api.get(`/api/cameras/${cameraId}/resolved-config`),
  })

  if (isLoading)
    return (
      <p role="status" aria-label="Loading config">
        Loading…
      </p>
    )

  const settings = (data as { settings?: Record<string, { value: unknown; source: string }> })
    ?.settings

  return (
    <div className="overflow-auto">
      <table className="w-full text-[13px] font-mono">
        <thead className="bg-surface-sunken border-b border-border">
          <tr>
            <th className="text-left px-4 py-2 text-text-muted font-medium">Key</th>
            <th className="text-left px-4 py-2 text-text-muted font-medium">Value</th>
            <th className="text-left px-4 py-2 text-text-muted font-medium">Source</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {settings &&
            Object.entries(settings).map(([key, item]) => (
              <tr key={key} className="hover:bg-surface-raised">
                <td className="px-4 py-2 text-text-secondary">{key}</td>
                <td className="px-4 py-2 text-text-primary">{JSON.stringify(item.value)}</td>
                <td className="px-4 py-2 text-text-muted">{item.source}</td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  )
}
