import * as Dialog from '@radix-ui/react-dialog'
import { useEffect, useRef } from 'react'
import Hls from 'hls.js'
import { Link } from 'react-router-dom'
import type { ForensicClip } from '@/shared/api/types'

interface ClipDrawerProps {
  clip: ForensicClip
  onClose: () => void
}

export function ClipDrawer({ clip, onClose }: ClipDrawerProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const hlsUrl = clip.clip_url

  useEffect(() => {
    const video = videoRef.current
    if (!video || !hlsUrl) return

    if (Hls.isSupported()) {
      const hls = new Hls()
      hls.loadSource(hlsUrl)
      hls.attachMedia(video)
      return () => hls.destroy()
    }

    if (video.canPlayType('application/vnd.apple.mpegurl')) {
      video.src = hlsUrl
    }
  }, [hlsUrl])

  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50" />
        <Dialog.Content
          className="fixed inset-y-0 right-0 z-50 flex w-[480px] flex-col bg-surface-base shadow-3 focus:outline-none"
          aria-label="Clip details"
        >
          <div className="flex items-center justify-between border-b border-border-DEFAULT px-4 py-3">
            <Dialog.Title className="text-[15px] font-semibold text-text-primary">
              Clip — Camera {clip.camera_id}
            </Dialog.Title>
            <Dialog.Close asChild>
              <button
                aria-label="Close drawer"
                className="rounded p-1 text-text-muted hover:bg-surface-sunken"
              >
                ✕
              </button>
            </Dialog.Close>
          </div>

          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            <div className="aspect-video overflow-hidden rounded-lg bg-black">
              {hlsUrl ? (
                <video
                  ref={videoRef}
                  className="h-full w-full"
                  autoPlay
                  muted
                  playsInline
                  controls
                  aria-label="Clip video"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-[13px] text-text-muted">
                  Video clip unavailable
                </div>
              )}
            </div>

            <dl className="space-y-2 text-[13px]">
              <div className="flex gap-2">
                <dt className="text-text-muted">Track ID</dt>
                <dd className="font-mono text-text-primary">{clip.global_track_id}</dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-text-muted">Camera</dt>
                <dd className="text-text-primary">{clip.camera_id}</dd>
              </div>
              {clip.zone_id != null && (
                <div className="flex gap-2">
                  <dt className="text-text-muted">Zone</dt>
                  <dd className="text-text-primary">{clip.zone_id}</dd>
                </div>
              )}
              <div className="flex gap-2">
                <dt className="text-text-muted">Time</dt>
                <dd className="text-text-primary">
                  {new Date(clip.triggered_at).toLocaleString()}
                </dd>
              </div>
              <div className="flex gap-2">
                <dt className="text-text-muted">Score</dt>
                <dd className="text-text-primary">{(clip.score * 100).toFixed(1)}%</dd>
              </div>
              {clip.duration_s != null && (
                <div className="flex gap-2">
                  <dt className="text-text-muted">Duration</dt>
                  <dd className="text-text-primary">{clip.duration_s}s</dd>
                </div>
              )}
            </dl>

            <Link
              to={`/analytics?open_scrubber=track_${clip.global_track_id}`}
              className="block rounded-md border border-border-DEFAULT px-3 py-2 text-center text-[13px] text-text-secondary hover:bg-surface-sunken"
              onClick={onClose}
            >
              Open in timeline scrubber
            </Link>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
