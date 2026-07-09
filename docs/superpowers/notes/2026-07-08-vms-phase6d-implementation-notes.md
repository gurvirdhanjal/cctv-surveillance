# Phase 6d — NVDEC GPU Decode — Implementation Notes

Companion to `docs/superpowers/plans/2026-07-08-vms-phase6d-nvdec-gpu-decode.md`.

## Session 2026-07-09 — Tasks 1–7 + Task 0 instrumentation (software complete)

### Task 0 capability check (this workstation)

- GPU: **NVIDIA RTX 2000 Ada Generation**, driver **595.71**, `nvdec_units=1`
  (GpuProfile probe).
- No system FFmpeg existed. Installed **gyan.dev ffmpeg-release-essentials** into
  `tools/ffmpeg/bin/` (gitignored — never commit binaries). `-decoders` confirms
  `h264_cuvid` + `hevc_cuvid` (plus av1/vp9/mjpeg cuvid). Wire via
  `VMS_NVDEC_FFMPEG_PATH=tools/ffmpeg/bin/ffmpeg.exe` (commented block added to `.env`).
- **Live-camera baseline run still pending** — the decode_ms/CPU% instrumentation is in
  the test pipeline; run `multi_cam_pipeline_test.py` (CPU) then `--nvdec` on the
  standard camera set and record the before/after table here (Task 8 gate input).

### Decisions & deviations

- Decoder factory is **URL-keyed** (`Callable[[str], DecodeBackend]`), not
  CameraConfig-keyed as the plan sketched — the worker's analytics-substream <640px
  fallback needs to reopen by URL. The worker's default factory closes over camera_id/
  width/height and calls `create_decoder`.
- `NvdecDecoder` returns **read-only** frames (`np.frombuffer`) — SHM write copies
  anyway; no per-frame copy added (6 MB/frame at 1080p).
- Reap grace (`_TERMINATE_GRACE_S=2.0`) is a module constant, not config — it is
  shutdown hygiene, not a tuning knob; the worker's `rtsp_failure_threshold` governs
  giving up.
- Test pipeline `--nvdec` decodes at `--nvdec-size` (default 1920x1080, the production
  analytics resolution) because cuvid `-resize` needs a target; the CPU path stays at
  native resolution. Comparisons must account for this.
- Script `--nvdec` sets `VMS_GPU_NVDEC_ENABLED=true` + `get_settings.cache_clear()`
  before first settings use — the ladder honours the run flag regardless of `.env`.

### Task 7 integration results (REAL GPU, 2026-07-09)

All 4 tests pass in 4.6 s on the RTX 2000 Ada with the tools/ffmpeg build:

| Test | Result |
|---|---|
| H.264 parity vs OpenCV | 60/60 frames, mean-abs-diff < 3 LSB at first/mid/last frame |
| HEVC parity vs OpenCV | 60/60 frames, MAD < 3 LSB (libx265 present in essentials build) |
| NVDEC `-resize` | frames arrive pre-sized (640x360), MAD < 12 vs cv2.resize reference |
| Ladder + lifecycle | 4 concurrent NVDEC sessions via full `create_decoder` ladder (ffprobe codec probe included), ledger drains to 0, zero leaked ffmpeg children |

This is the §6.3 **decode-parity gate: PASS**. The detection-parity gate (face/body
rates on live cameras, CAM141/144 canary) remains for Task 8.

### Suite-wide fix found during Task 2

`alembic/env.py` called `fileConfig()` without `disable_existing_loggers=False`, so the
conftest's session migration silently disabled every already-imported `vms.*` logger.
All caplog assertions were impossible (and prior log-absence tests passed vacuously).
One-line fix; benefits every future log test and in-process alembic runs.

### Gotchas

- `# noqa` on a multi-line import must sit on the FIRST line — black re-wrapping moved
  them to the closing paren where ruff ignores them. Kept the script's post-DLL-injection
  imports single-line.
- pytest `caplog` + lazy logging: assert on `record.getMessage()`, never `record.message`.

## Remaining (hardware session)

1. **Task 0 baseline run**: CPU decode table (decode_ms p50/p95, process CPU%, fps,
   drops) on the standard camera set.
2. **Task 8 gates**: same set with `--nvdec` — CPU% drop ≥70% of decode share, no
   dropped/stale increase, detection-parity with CAM141/144 canary; capacity probe
   (streams per NVDEC unit, then set the informed `VMS_NVDEC_MAX_SESSIONS` default);
   failure drills (kill ffmpeg child mid-run, block RTSP).
3. **Task 9 close-out**: update GPU spec §6.3 with measured numbers, CLAUDE.md §3,
   plan → COMPLETE.
