import { Navigate } from 'react-router-dom'

/** Guard landing — redirects to the live view. */
export function GuardView() {
  return <Navigate to="/live" replace />
}
