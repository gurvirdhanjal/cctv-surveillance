import { useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { useLiveStore } from './store/liveStore'
import { LivePage } from './LivePage'

/**
 * Route `/live/cameras/:cameraId` — deep-links to a specific camera by setting
 * focusedCameraId in liveStore before rendering the standard LivePage layout.
 */
export function FocusedCameraPage() {
  const { cameraId } = useParams<{ cameraId: string }>()
  const setFocusedCamera = useLiveStore((s) => s.setFocusedCamera)

  useEffect(() => {
    const id = cameraId ? parseInt(cameraId, 10) : NaN
    if (!isNaN(id)) setFocusedCamera(id)
  }, [cameraId, setFocusedCamera])

  return <LivePage />
}
