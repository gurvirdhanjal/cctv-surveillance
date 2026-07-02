import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const { HomographyCalibrator } = await import('./HomographyCalibrator')

function renderCalibrator(props?: Partial<Parameters<typeof HomographyCalibrator>[0]>) {
  return render(
    <MemoryRouter>
      <HomographyCalibrator cameraId={3} {...props} />
    </MemoryRouter>,
  )
}

describe('HomographyCalibrator', () => {
  it('renders start state by default', () => {
    renderCalibrator()
    expect(screen.getByRole('button', { name: 'Start calibration' })).toBeInTheDocument()
  })

  it('advances to pick_frame step on Start', () => {
    renderCalibrator()
    fireEvent.click(screen.getByRole('button', { name: 'Start calibration' }))
    expect(screen.getByRole('img', { name: 'Frame point picker' })).toBeInTheDocument()
  })

  it('Next is disabled in pick_frame until 4 points are picked', () => {
    renderCalibrator({ initialStep: 'pick_frame' })
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
  })

  it('Next enables after 4 frame points are clicked', () => {
    renderCalibrator({ initialStep: 'pick_frame' })
    const picker = screen.getByRole('img', { name: 'Frame point picker' })
    for (let i = 0; i < 4; i++) {
      fireEvent.click(picker, { clientX: 10 + i * 20, clientY: 10 + i * 20 })
    }
    expect(screen.getByRole('button', { name: 'Next' })).not.toBeDisabled()
  })

  it('renders review step via initialStep', () => {
    renderCalibrator({ initialStep: 'review', initialReprErr: 1.2 })
    expect(screen.getByText(/Reprojection error/)).toBeInTheDocument()
    expect(screen.getByText('1.20 px')).toBeInTheDocument()
  })

  it('Save homography is enabled when reprErr < 2', () => {
    renderCalibrator({ initialStep: 'review', initialReprErr: 1.2 })
    expect(screen.getByRole('button', { name: 'Save homography' })).not.toBeDisabled()
  })

  it('Save homography is disabled when reprErr >= 2', () => {
    renderCalibrator({ initialStep: 'review', initialReprErr: 2.5 })
    expect(screen.getByRole('button', { name: 'Save homography' })).toBeDisabled()
  })

  it('transitions to done after Save', () => {
    renderCalibrator({ initialStep: 'review', initialReprErr: 1.2 })
    fireEvent.click(screen.getByRole('button', { name: 'Save homography' }))
    expect(screen.getByText('Calibration saved successfully.')).toBeInTheDocument()
  })

  it('Recalibrate resets to start', () => {
    renderCalibrator({ initialStep: 'review', initialReprErr: 2.5 })
    fireEvent.click(screen.getByRole('button', { name: 'Recalibrate' }))
    expect(screen.getByRole('button', { name: 'Start calibration' })).toBeInTheDocument()
  })
})
