import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { useLiveStore } from '../store/liveStore'

export function OfflineReconnectBanner() {
  const wsStatus = useLiveStore((s) => s.wsStatus)
  const shouldReduce = useReducedMotion()
  const visible = wsStatus === 'reconnecting' || wsStatus === 'offline'

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          role="status"
          aria-live="polite"
          initial={shouldReduce ? false : { y: -40 }}
          animate={{ y: 0 }}
          exit={shouldReduce ? {} : { y: -40 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-x-0 top-0 z-50 flex h-9 items-center justify-center bg-amber-500 text-sm font-medium text-slate-900"
        >
          {wsStatus === 'reconnecting' ? (
            <>
              <span
                className="mr-2 h-3.5 w-3.5 animate-spin rounded-full border-2 border-slate-900/30 border-t-slate-900"
                aria-hidden="true"
              />
              Reconnecting to live feed&hellip;
            </>
          ) : (
            'Live feed disconnected. Retrying…'
          )}
        </motion.div>
      )}
    </AnimatePresence>
  )
}
