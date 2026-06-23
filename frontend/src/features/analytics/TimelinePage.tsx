import { Helmet } from 'react-helmet-async'
import { TimeScrubber } from './components/TimeScrubber'

export function TimelinePage() {
  return (
    <>
      <Helmet title="Timeline" />
      <div className="space-y-4">
        <h1 className="text-[20px] font-semibold text-text-primary">Timeline</h1>
        <TimeScrubber disabled />
      </div>
    </>
  )
}
