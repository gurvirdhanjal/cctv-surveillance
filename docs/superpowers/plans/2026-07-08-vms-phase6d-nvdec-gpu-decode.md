# Phase 6d — NVDEC GPU Stream Decode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: IN PROGRESS — started 2026-07-09 (Task 0 capability check + instrumentation;
live-camera baseline run and Task 8 validation deferred to the hardware session)**

**Goal:** Move RTSP H.264/H.265 stream decoding from CPU (OpenCV/FFmpeg software) to the
GPU's dedicated NVDEC video engine. The §6.3 build trigger is met: the user confirmed on
2026-07-08 that CPU decode is the observed bottleneck on live multi-camera runs. Success =
CPU decode load drops materially, dropped/stale frames do not increase, and frame content
is equivalent enough that face/body detection rates are unchanged (frames stay accurately
bound to persons).

**Architecture:** A `DecodeBackend` protocol in `vms/ingestion/decoder.py` (same pattern
as `InferenceBackend` from Phase 6c) with two implementations selected by a factory:
`OpenCvDecoder` (current `cv2.VideoCapture` behaviour, extracted unchanged) and
`NvdecDecoder` — an **FFmpeg `h264_cuvid`/`hevc_cuvid` subprocess** emitting raw `bgr24`
frames over a pipe, with NVDEC-side `-resize` to the camera's analytics resolution.
Per GPU spec §6.3 this is the prescribed Windows approach; Video Codec SDK ctypes bindings
are explicitly out of scope. A thread-safe session ledger caps concurrent NVDEC sessions
(consumer cards have 1–2 NVDEC units); overflow cameras fall back to CPU decode with an
explicit WARNING — never silently. `IngestionWorker` swaps `cv2.VideoCapture` for the
factory; everything downstream (SHM slot, FramePointer, Redis stream) is untouched.

```
gpu_nvdec_enabled=False ──────────────────────────────► OpenCvDecoder (today's path)
gpu_nvdec_enabled=True ─► nvdec_available()? ─ no ────► OpenCvDecoder + WARNING
                              │ yes
                          probe_codec(url)? ─ fail ───► OpenCvDecoder + WARNING
                              │ h264 | hevc
                          ledger.acquire()? ─ full ───► OpenCvDecoder + WARNING (cap logged)
                              │ ok
                          NvdecDecoder ── open fails ─► release slot ► OpenCvDecoder + WARNING
```

**Tech Stack:** FFmpeg (build must include `h264_cuvid`/`hevc_cuvid` — verify with
`ffmpeg -decoders`), ffprobe, subprocess pipes, numpy, existing `GpuProfile.nvdec_units`
probe, pytest (unit tests GPU-free via stubbed Popen; integration tests hardware-gated).

**Spec refs:** `2026-06-13-vms-gpu-acceleration.md` §6.3 (canonical — approach, probe,
gates), §G.1 (decode ceiling);
`2026-07-08-vms-model-stack-and-analytics-readiness.md` §4.4 (activation record, gap 12);
CLAUDE.md §0.6 (`ingestion/worker.py` is a performance-sensitive path — measure
before/after), §7.2 (RTSP URLs contain credentials — never logged at INFO).

**Non-goals (stay out of scope):**
- INT8 quantization (the other half of "Phase 6d" in older notes) — still deferred, only
  needed past 52 cameras.
- Zero-copy GPU decode→inference (DeepStream-style). Frames still cross to CPU/SHM because
  preprocessing is CPU-side; the win here is offloading decode compute, honestly stated.
- NVDEC for the recording path (recording spec owns that).
- NVENC anything.

**Quality gate (every task):**
```powershell
black vms/ tests/ scripts/; ruff check vms/ tests/ scripts/; mypy vms/; pytest
```

**Config additions (all in `vms/config.py`, no bare literals anywhere):**

| Setting | Default | Meaning |
|---|---|---|
| `gpu_nvdec_enabled` | `False` (exists) | Master switch |
| `nvdec_ffmpeg_path` | `"ffmpeg"` | FFmpeg binary (allows a cuvid-enabled build side-by-side) |
| `nvdec_ffprobe_path` | `"ffprobe"` | ffprobe binary |
| `nvdec_max_sessions` | `12` | Concurrent NVDEC decoder cap; conservative until Task 8 measures the real ceiling |
| `nvdec_probe_timeout_s` | `10` | ffprobe codec-probe timeout per camera |
| `nvdec_restart_after_failures` | `3` | Consecutive short-reads before the decoder transparently restarts its subprocess (bounded; worker's `rtsp_failure_threshold` still governs giving up) |

---

## Task 0 — Baseline measurement (hardware session; §6.3 "measure before/after")

The trigger is user-observed; this task quantifies it so Task 8 has a comparison row.
No production code changes beyond instrumentation.

- [ ] Add decode-time instrumentation to `scripts/multi_cam_pipeline_test.py`: wall-clock
      of each blocking frame read (the decode cost) as `decode_ms` p50/p95 per camera in
      the periodic stats block, plus whole-process CPU % (psutil) in the global footer.
- [ ] Run the standard multi-camera set (same cameras as the Phase 6b Task 5
      characterization runs, production thresholds). Record per camera: resolution, codec
      (H.264/H.265), fps delivered, `decode_ms` p50/p95, dropped/stale frame count, and
      total process CPU %.
- [ ] Write the baseline table into
      `docs/superpowers/notes/2026-07-08-vms-phase6d-implementation-notes.md` (create the
      notes file with this task). This table is the before-row for the Task 8 gate.
- [ ] Capability check on the target machine, recorded in the notes:
      `ffmpeg -decoders | findstr cuvid` (must list `h264_cuvid` + `hevc_cuvid`) and
      `ffprobe -version`. If the installed FFmpeg lacks cuvid, note the replacement build
      used and pin its version.
- [ ] Verify: gate green (instrumentation is display-only; no behaviour change).

## Task 1 — `DecodeBackend` protocol + `OpenCvDecoder` extraction (pure refactor)

Behaviour must be byte-for-byte identical to today. Every changed line traces to moving
capture behind an interface.

- [x] Failing tests first (`tests/test_ingestion_decoder.py`):
      `DecodeBackend` is a `@runtime_checkable` Protocol with
      `read() -> tuple[bool, np.ndarray | None]`, `get_resolution() -> tuple[int, int]`
      (0,0 when unknown — mirrors current best-effort RTSP behaviour), `release() -> None`.
      `OpenCvDecoder` satisfies it; constructor applies `CAP_PROP_BUFFERSIZE=1`
      (regression test via a fake `VideoCapture` asserting the property call).
- [x] Failing test: `IngestionWorker` accepts an injected decoder factory
      (`Callable[[str], DecodeBackend]`, default `OpenCvDecoder` — URL-keyed, not
      CameraConfig-keyed, so the analytics-substream fallback can reopen by URL) and
      its capture loop runs against a fake decoder (frame published, decoder released).
- [x] Implement: `vms/ingestion/decoder.py`; refactor `worker.py::_capture_loop` to use
      the factory. The analytics-substream <640px fallback check stays in the worker,
      now reading `decoder.get_resolution()`. Blocking `read()` stays in the shared
      executor (the comment about pool sizing stays).
      → existing `test_ingestion_worker.py` patch targets moved to
      `vms.ingestion.decoder.cv2.VideoCapture` (tests follow code).
- [x] Verify: full existing ingestion test suite green unchanged; gate green
      (935 passed, 2026-07-09).

## Task 2 — Capability + codec probes

- [x] Failing tests (all subprocess calls stubbed — CI has no GPU/FFmpeg):
      `nvdec_available(settings) -> bool` is True only when (a) `ffmpeg -decoders`
      output contains `h264_cuvid` AND (b) `detect_gpu_profile().nvdec_units >= 1`;
      result `lru_cache`d; FFmpeg binary missing → False + one WARNING (not an exception).
- [x] Failing tests: `probe_codec(rtsp_url, settings) -> str | None` runs ffprobe
      (`-select_streams v:0 -show_entries stream=codec_name`) with
      `nvdec_probe_timeout_s`; returns `"h264"` / `"hevc"`; timeout, non-zero exit, or
      unknown codec → `None`.
- [x] Security tests (§7.2): capture logs during both probes with a URL containing
      `user:secret@host` — assert `secret` appears in NO log record at any level; log
      lines carry `camera_id` only. (ffprobe argv contains the URL by necessity; the
      assertion is about our log output.)
- [x] Implement in `vms/ingestion/decoder.py` with a small `_mask_url()` helper used by
      every log call in this module.
      → config settings (`VMS_NVDEC_FFMPEG_PATH`/`FFPROBE_PATH`/`PROBE_TIMEOUT_S`/
      `MAX_SESSIONS`/`RESTART_AFTER_FAILURES`) added here since the probes consume them.
      → **Suite-wide fix found:** `alembic/env.py` `fileConfig()` was silencing all
      pre-imported `vms.*` loggers (`disable_existing_loggers` defaulted True) — caplog
      assertions were impossible and earlier log-absence tests passed vacuously. Fixed
      with `disable_existing_loggers=False`.
- [x] Verify: gate green (943 passed, 2026-07-09).

## Task 3 — `NvdecDecoder` (FFmpeg subprocess)

Reference command (h264; hevc swaps the decoder name):

```
ffmpeg -nostdin -loglevel warning -rtsp_transport tcp
       -c:v h264_cuvid -resize {W}x{H}
       -i {rtsp_url}
       -f rawvideo -pix_fmt bgr24 pipe:1
```

`-resize` is a cuvid private option (must precede `-i`) — scaling happens on the NVDEC
engine, so the pipe carries analytics-resolution frames, not source resolution. Frame
framing is exact: `W*H*3` bytes per frame.

- [x] Failing tests — command builder (pure function, exhaustive):
      correct decoder per codec; `-resize` before `-i`; `-rtsp_transport tcp` present for
      `rtsp://` inputs and absent for file inputs (file support is what the integration
      tests use); output is `bgr24` rawvideo to `pipe:1`; uses `nvdec_ffmpeg_path`.
- [x] Failing tests — read loop, via a stubbed Popen factory (a fake process object whose
      stdout serves scripted bytes; no real FFmpeg in unit tests):
      * exact framing: stdout serving 3 frames of `W*H*3` bytes → 3 successful reads,
        each `(True, ndarray)` with shape `(H, W, 3)` dtype uint8;
      * short read / EOF → `(False, None)`;
      * transparent restart: after `nvdec_restart_after_failures` consecutive failed
        reads the decoder kills + relaunches the subprocess exactly once per burst
        (assert Popen factory call count), then failure counting resets on success;
      * `release()` terminates the process, escalates to kill after a bounded wait, and
        reaps it (no zombie — assert `wait()` called); idempotent double-release.
- [x] Failing tests — stderr drain: a daemon thread consumes stderr and logs at DEBUG
      with `_mask_url()` applied (same `secret`-absence assertion as Task 2);
      pipe `bufsize` ≥ 2 frames so FFmpeg never blocks on a slow consumer.
- [x] Failing test — `get_resolution()` returns the configured `(W, H)` (frames are
      resized decoder-side, so the worker's resize branch becomes a no-op on this path —
      assert the worker skips `cv2.resize` for correctly-sized frames, which is existing
      behaviour).
- [x] Implement `NvdecDecoder` in `vms/ingestion/decoder.py`.
- [x] Verify: gate green (951 passed, 2026-07-09).

## Task 4 — Session ledger + fallback ladder (no camera goes dark, no silent fallback)

- [x] Failing tests: `NvdecSessionLedger` — thread-safe acquire/release against
      `nvdec_max_sessions`; acquire beyond cap returns False; release frees a slot;
      concurrent acquire from threads never over-allocates (hammer test).
- [x] Failing tests — `create_decoder(camera, settings)` factory, every ladder branch
      from the Architecture diagram:
      * `gpu_nvdec_enabled=False` → `OpenCvDecoder`, no probes run (assert stubs not called);
      * enabled but `nvdec_available()` False → `OpenCvDecoder` + one WARNING;
      * codec probe `None` → `OpenCvDecoder` + WARNING naming the camera_id;
      * ledger full → `OpenCvDecoder` + WARNING `"NVDEC session cap (N) reached"` —
        the spec's no-silent-truncation rule, tested by asserting the log record;
      * `NvdecDecoder` construction/first-open raises → ledger slot released (assert
        count) → `OpenCvDecoder` fallback; camera still delivers frames;
      * `NvdecDecoder.release()` releases its ledger slot (test via factory-wired
        callback).
- [x] Implement ledger + factory in `vms/ingestion/decoder.py`.
- [x] Verify: gate green (959 passed, 2026-07-09).

## Task 5 — Worker + config integration

- [ ] Config: add the five new settings to `vms/config.py` with the defaults from the
      table above; failing test asserts env-var override round-trip (`VMS_NVDEC_*`).
- [ ] Failing tests — worker behaviour: default factory is `create_decoder`;
      with `gpu_nvdec_enabled=False` the worker path is regression-identical (existing
      suite is the proof); with enabled+ladder-fallback the worker runs on
      `OpenCvDecoder` without marking the camera inactive; read-failure → existing
      backoff → `rtsp_failure_threshold` → `_mark_camera_inactive()` semantics unchanged
      on BOTH decoder types (parametrized test).
- [ ] Update `.env.example` (or the deploy runbook section that documents env vars) with
      the `VMS_NVDEC_*` block + the FFmpeg-with-cuvid prerequisite note.
- [ ] Verify: gate green.

## Task 6 — Test-pipeline integration (`scripts/multi_cam_pipeline_test.py`)

The characterization tool must exercise the same decode path production uses, or Task 5
(Phase 6b) camera characterization and this phase's validation diverge.

- [ ] `--nvdec` CLI flag: reader threads obtain their capture via `create_decoder`
      instead of raw `cv2.VideoCapture`; without the flag, behaviour unchanged.
- [ ] Per-camera HUD line + periodic stats gain: decode path label (`NVDEC` / `CPU`) and
      the Task 0 `decode_ms` metric, so before/after runs are directly comparable
      on-screen.
- [ ] Dry-run smoke: `--dry-run --nvdec` on a machine without cuvid exits cleanly on the
      CPU fallback path (ladder WARNING visible) — manual check recorded in notes.
- [ ] Verify: gate green (script is ruff/mypy-covered).

## Task 7 — Automated integration tests (decode parity)

`@pytest.mark.integration`, plus `@pytest.mark.skipif` on `not nvdec_available()` — they
run on the GPU workstation, not CI. Test clips are **generated at test time** (never
committed binaries):

```
ffmpeg -f lavfi -i testsrc2=size=1280x720:rate=15:duration=4 -c:v libx264 -pix_fmt yuv420p {tmp}/ref_h264.mp4
ffmpeg -f lavfi -i testsrc2=size=1280x720:rate=15:duration=4 -c:v libx265 -pix_fmt yuv420p {tmp}/ref_hevc.mp4   # skipped if libx265 absent
```

- [ ] Failing test — H.264 parity: decode `ref_h264.mp4` fully through `NvdecDecoder`
      (file input) and `OpenCvDecoder`; assert identical frame count, identical shape
      `(720, 1280, 3)`, and per-frame mean absolute pixel difference below a small
      tolerance (cuvid vs software YUV→BGR conversion differs by a few LSBs; the
      tolerance is a named constant in the test with a comment, not a config value).
- [ ] Failing test — HEVC parity: same via `hevc_cuvid` (skipped when the encoder or
      decoder is unavailable, with an explicit skip reason).
- [ ] Failing test — resize parity: decode with `-resize 640x360` → frames arrive
      pre-sized `(360, 640, 3)`; content matches an OpenCV decode + `cv2.resize` of the
      same clip within a looser tolerance (different scalers).
- [ ] Failing test — lifecycle under load: open 4 concurrent `NvdecDecoder`s on the same
      file, read all frames, release; ledger returns to zero; no zombie ffmpeg processes
      remain (enumerate child processes via psutil before/after).
- [ ] Verify: `pytest -m integration tests/ingestion/` green on the GPU workstation;
      full gate green.

## Task 8 — Hardware validation session (the §6.3 gates + capacity probe)

Live-camera session on the GPU workstation. Every number lands in the notes file next to
the Task 0 baseline.

- [ ] **Before/after gate:** re-run the exact Task 0 configuration with `--nvdec`.
      PASS requires: (a) whole-process CPU % drops materially (target: decode
      contribution cut by ≥70%); (b) per-camera `decode_ms` p95 below the CPU baseline;
      (c) dropped/stale frame counts (SHM staleness guard + reader stats) do not
      increase; (d) delivered fps per camera unchanged.
- [ ] **Detection-parity gate (frames stay bound to persons):** run the same cameras,
      same duration, same production thresholds, CPU vs NVDEC. Face-detect %,
      face-embed %, body-embed counts, and quality distributions (p5–p95) per camera
      must match within run-to-run noise. Canary rule from Phase 6b applies: if
      CAM141/CAM144 face-embed rate shifts beyond noise, STOP and investigate the
      colorspace conversion before proceeding.
- [ ] **Capacity probe:** add streams one at a time (loop recorded clips if live cameras
      run out) while watching `nvidia-smi dmon` dec-util; record streams sustained per
      NVDEC unit at target fps for H.264 and H.265. Set the informed
      `nvdec_max_sessions` default from this number (change the config default + note
      why). If the ceiling is below the deployment's camera count, the ladder's explicit
      CPU-fallback WARNING is the designed behaviour — document the split.
- [ ] **Failure drills:** kill an ffmpeg child mid-run → transparent restart within
      `nvdec_restart_after_failures` reads, no worker death; unplug/block one RTSP
      source → existing backoff + inactive-marking behaviour confirmed on the NVDEC path.
- [ ] Update GPU spec §6.3 with the measured numbers (spec gate line: "CPU decode load
      drops materially; no increase in dropped/stale frames" — record PASS/FAIL
      explicitly).
- [ ] Verify: notes updated with all four tables; gate green.

## Task 9 — Phase close-out

- [ ] Full quality gate + `pytest -m integration` on the GPU workstation both green.
- [ ] Coverage ≥ 70% on `vms/ingestion/` (decoder module fully unit-covered without GPU).
- [ ] `docs/superpowers/notes/2026-07-08-vms-phase6d-implementation-notes.md` complete:
      baseline table, after table, detection-parity table, capacity numbers, decisions +
      surprises.
- [ ] CLAUDE.md §3 updated (Phase 6d status; the "Defer: Phase 6d INT8/NVDEC" line
      rewritten — NVDEC done, INT8 still deferred); model-stack spec gap 12 marked DONE.
- [ ] Plan Status → COMPLETE. Conventional commits throughout (one logical change each;
      no AI co-author footer).

---

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Consumer-card NVDEC unit ceiling silently caps decode | Ledger + explicit WARNING per overflowed camera (Task 4); real ceiling measured in Task 8; `GpuProfile.nvdec_units` probe gates availability |
| Installed FFmpeg lacks cuvid decoders | `nvdec_available()` capability probe → clean CPU fallback + WARNING; prerequisite documented in Task 0/Task 5 runbook note |
| cuvid YUV→BGR colorspace shift changes detection behaviour | Task 7 pixel-tolerance parity tests + Task 8 detection-parity gate with the CAM141/CAM144 canary rule |
| Zombie/leaked ffmpeg subprocesses | `release()` terminate→kill→reap tested (Task 3); psutil child-process sweep in Task 7 lifecycle test |
| Pipe copy overhead eats the decode win (BGR24 1080p ≈ 6 MB/frame) | NVDEC-side `-resize` to analytics resolution shrinks the pipe payload; Task 8 before/after gate is the arbiter — if CPU% doesn't drop, the phase fails its own gate honestly |
| RTSP credentials leak via ffmpeg/ffprobe logging | `_mask_url()` on every log call in the module; explicit secret-absence tests in Tasks 2 and 3 (§7.2) |
| Worker is a §0.6 performance-sensitive path | Task 1 is a pure refactor proven by the existing suite; all new work sits behind the factory; Task 0/8 measure before/after |
