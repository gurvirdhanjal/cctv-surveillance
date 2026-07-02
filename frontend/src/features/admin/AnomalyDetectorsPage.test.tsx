import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { HelmetProvider } from 'react-helmet-async'

vi.mock('@/shared/api/client', () => ({ api: { get: vi.fn(), patch: vi.fn() } }))

import { api } from '@/shared/api/client'
const { AnomalyDetectorsPage } = await import('./AnomalyDetectorsPage')

const DETECTORS = [
  {
    detector_id: 1,
    alert_type: 'INTRUSION',
    class_path: 'vms.anomaly.intrusion.IntrusionDetector',
    is_enabled: true,
    config_json: null,
    model_version: 'yolov8l-pose-v2',
  },
  {
    detector_id: 2,
    alert_type: 'VIOLENCE',
    class_path: 'vms.anomaly.violence.ViolenceDetector',
    is_enabled: false,
    config_json: null,
    model_version: null,
  },
]

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
}

function renderPage() {
  return render(
    <HelmetProvider>
      <QueryClientProvider client={makeClient()}>
        <MemoryRouter>
          <AnomalyDetectorsPage />
        </MemoryRouter>
      </QueryClientProvider>
    </HelmetProvider>,
  )
}

describe('AnomalyDetectorsPage', () => {
  beforeEach(() => {
    vi.mocked(api.get).mockReset()
    vi.mocked(api.patch).mockReset()
  })

  it('renders page heading', () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    expect(screen.getByRole('heading', { name: 'Anomaly Detectors' })).toBeInTheDocument()
  })

  it('renders detector list', async () => {
    vi.mocked(api.get).mockResolvedValue(DETECTORS)
    renderPage()
    expect(await screen.findByText('INTRUSION')).toBeInTheDocument()
    expect(screen.getByText('VIOLENCE')).toBeInTheDocument()
  })

  it('renders enable/disable toggle switches', async () => {
    vi.mocked(api.get).mockResolvedValue(DETECTORS)
    renderPage()
    const enabledSwitch = await screen.findByRole('switch', { name: 'Disable INTRUSION' })
    expect(enabledSwitch).toHaveAttribute('aria-checked', 'true')
    const disabledSwitch = screen.getByRole('switch', { name: 'Enable VIOLENCE' })
    expect(disabledSwitch).toHaveAttribute('aria-checked', 'false')
  })

  it('calls PATCH /api/anomaly-detectors/:id on toggle', async () => {
    vi.mocked(api.get).mockResolvedValue(DETECTORS)
    vi.mocked(api.patch).mockResolvedValue({})
    renderPage()
    const toggle = await screen.findByRole('switch', { name: 'Disable INTRUSION' })
    fireEvent.click(toggle)
    await waitFor(() => {
      expect(vi.mocked(api.patch)).toHaveBeenCalledWith('/api/anomaly-detectors/1', {
        is_enabled: false,
      })
    })
  })

  it('shows empty state when no detectors', async () => {
    vi.mocked(api.get).mockResolvedValue([])
    renderPage()
    expect(await screen.findByText(/No anomaly detectors configured/)).toBeInTheDocument()
  })
})
