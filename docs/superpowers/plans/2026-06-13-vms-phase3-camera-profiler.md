# CameraProfiler & Site Readiness Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE**

**Goal:** Implement `CameraProfiler` — an RTSP probe that measures actual stream quality, assigns a capability tier (FULL/MID/LOW), detects shutter type, and generates a Site Readiness Report PDF. Wire it into the existing `POST /api/cameras/{id}/profile` endpoint stub and add `GET /api/sites/readiness-report.pdf`.

**Architecture:** A standalone `vms/profiler/` module with three units: `TierAssigner` (pure CPU-side logic), `CameraProfiler` (I/O: opens RTSP, samples frames via OpenCV), and `SiteReadinessPDF` (builds a reportlab PDF). The two API endpoints delegate to these. No new DB table or Alembic migration is needed — `Camera.capability_tier`, `.profile_data`, `.profiled_at`, `.shutter_type` already exist in models.py.

**Tech Stack:** Python 3.11, OpenCV (`cv2`), NumPy, ReportLab (already in requirements.txt), FastAPI, SQLAlchemy.

**Spec refs:** v2-hardened-design.md §B, §L.3.1

---

## File map

| Action | Path |
|---|---|
| Create | `vms/profiler/__init__.py` |
| Create | `vms/profiler/tier.py` |
| Create | `vms/profiler/probe.py` |
| Create | `vms/profiler/report.py` |
| Modify | `vms/api/schemas.py` — extend `ProfileData`, `ProfileResponse` |
| Modify | `vms/api/routes/cameras.py` — update POST /profile stub, add GET /sites/readiness-report.pdf |
| Modify | `vms/config.py` — add profiler config vars |
| Create | `tests/profiler/__init__.py` |
| Create | `tests/profiler/test_tier.py` |
| Create | `tests/profiler/test_probe.py` |
| Create | `tests/profiler/test_report.py` |
| Modify | `tests/api/test_cameras.py` — add profile endpoint tests |

---

## Task 1: Add profiler config vars to config.py

**Files:**
- Modify: `vms/config.py`
- No test file (config is tested implicitly)

- [x] **Step 1: Add profiler settings to `Settings` class**

  Open `vms/config.py`. After the `maintenance_calendar_max_range_days` line, add:

  ```python
  # camera profiler
  profiler_probe_duration_s: int = 60       # live-measurement window
  profiler_sample_frames: int = 30          # frames for quality + shutter sampling
  profiler_shutter_skew_threshold: float = 0.04   # variance above which → rolling
  profiler_focus_full_min: float = 30.0     # Laplacian variance minimum for FULL tier
  profiler_focus_mid_min: float = 15.0      # minimum for MID tier (below = LOW)
  profiler_fps_full_min: float = 12.0       # fps minimum for FULL tier
  profiler_fps_mid_min: float = 8.0         # minimum for MID tier
  profiler_res_full_min_h: int = 1080       # height minimum for FULL tier
  profiler_res_mid_min_h: int = 720         # minimum for MID tier
  ```

- [x] **Step 2: Verify mypy still passes**

  ```powershell
  mypy vms/config.py
  ```

  Expected: `Success: no issues found in 1 source file`

- [x] **Step 3: Commit**

  ```powershell
  git add vms/config.py
  git commit -m "feat: add profiler config vars to Settings"
  ```

---

## Task 2: Extend ProfileData and ProfileResponse schemas

**Files:**
- Modify: `vms/api/schemas.py`

- [x] **Step 1: Write failing test for the new schema fields**

  Create `tests/profiler/__init__.py` (empty file).

  Open `tests/api/test_cameras.py` (or create it). Add:

  ```python
  def test_profile_data_full_fields() -> None:
      """ProfileData must accept the full set of measured fields."""
      from vms.api.schemas import ProfileData

      pd = ProfileData(
          resolution_w=1920,
          resolution_h=1080,
          fps_measured=15.0,
          focus_score=42.0,
          frame_drop_rate=0.02,
          brightness_mean=128.0,
          is_analog_via_encoder=False,
          tier_reason=">=1080p AND fps>=12 AND focus>=30",
          codec="H264",
          shutter_suggestion="rolling",
          shutter_confidence=0.82,
          suggested_tier="FULL",
      )
      assert pd.resolution_w == 1920
      assert pd.tier_reason == ">=1080p AND fps>=12 AND focus>=30"
  ```

- [x] **Step 2: Run to verify failure**

  ```powershell
  pytest tests/api/test_cameras.py::test_profile_data_full_fields -v
  ```

  Expected: `FAILED` — `ValidationError` because fields don't exist yet.

- [x] **Step 3: Extend `ProfileData` in schemas.py**

  Find the `class ProfileData(BaseModel):` block and add the missing fields:

  ```python
  class ProfileData(BaseModel):
      resolution_w: int | None = None
      resolution_h: int | None = None
      fps_measured: float | None = None
      focus_score: float | None = None
      frame_drop_rate: float | None = None       # fraction of frames that failed to decode
      brightness_mean: float | None = None       # mean pixel brightness [0–255]
      is_analog_via_encoder: bool | None = None  # deinterlace combing artifact detected
      tier_reason: str | None = None             # human-readable tier explanation
      codec: str | None = None                   # detected codec string e.g. "H264"
      shutter_suggestion: str | None = Field(default=None, pattern="^(rolling|global|unknown)$")
      shutter_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
      suggested_tier: str | None = Field(default=None, pattern="^(FULL|MID|LOW)$")
  ```

  Also extend `ProfileResponse` to include `tier_reason`:

  ```python
  class ProfileResponse(BaseModel):
      model_config = ConfigDict(from_attributes=False)

      camera_id: int
      profile_data: ProfileData | None
      profiled_at: datetime | None
      capability_tier: str
      shutter_type: str
      tier_reason: str | None = None   # extracted from profile_data.tier_reason
  ```

- [x] **Step 4: Update `GET /cameras/{id}/profile` to populate `tier_reason`**

  In `vms/api/routes/cameras.py`, find `get_profile()` and update the return:

  ```python
  @router.get("/cameras/{camera_id}/profile", response_model=ProfileResponse)
  def get_profile(
      camera_id: int,
      db: Session = Depends(get_db),
      _user: dict[str, Any] = Depends(get_current_user),
  ) -> ProfileResponse:
      cam = _get_camera_or_404(camera_id, db)
      profile_parsed: ProfileData | None = None
      if cam.profile_data:
          try:
              profile_parsed = ProfileData(**json.loads(cam.profile_data))
          except (json.JSONDecodeError, ValueError):
              profile_parsed = None
      return ProfileResponse(
          camera_id=cam.camera_id,
          profile_data=profile_parsed,
          profiled_at=cam.profiled_at,
          capability_tier=cam.capability_tier,
          shutter_type=cam.shutter_type,
          tier_reason=profile_parsed.tier_reason if profile_parsed else None,
      )
  ```

- [x] **Step 5: Run test to verify it passes**

  ```powershell
  pytest tests/api/test_cameras.py::test_profile_data_full_fields -v
  ```

  Expected: `PASSED`

- [x] **Step 6: Run full suite, fix any mypy issues**

  ```powershell
  mypy vms/api/schemas.py vms/api/routes/cameras.py
  pytest tests/api/ -v
  ```

- [x] **Step 7: Commit**

  ```powershell
  git add vms/api/schemas.py vms/api/routes/cameras.py tests/profiler/__init__.py tests/api/
  git commit -m "feat: extend ProfileData and ProfileResponse with measured fields"
  ```

---

## Task 3: TierAssigner — pure tier assignment logic

**Files:**
- Create: `vms/profiler/__init__.py`
- Create: `vms/profiler/tier.py`
- Create: `tests/profiler/test_tier.py`

- [x] **Step 1: Write failing tests**

  Create `tests/profiler/test_tier.py`:

  ```python
  """Tests for CameraProfiler tier assignment logic."""
  import pytest
  from vms.api.schemas import ProfileData
  from vms.profiler.tier import assign_tier


  def _data(**kwargs: object) -> ProfileData:
      """Helper: build ProfileData with sensible defaults, override via kwargs."""
      defaults: dict[str, object] = {
          "resolution_w": 1920,
          "resolution_h": 1080,
          "fps_measured": 15.0,
          "focus_score": 40.0,
          "is_analog_via_encoder": False,
          "frame_drop_rate": 0.01,
      }
      defaults.update(kwargs)
      return ProfileData(**defaults)


  def test_assign_tier_full_all_criteria_met() -> None:
      tier, reason = assign_tier(_data())
      assert tier == "FULL"
      assert "1080p" in reason or "fps" in reason


  def test_assign_tier_low_resolution() -> None:
      tier, reason = assign_tier(_data(resolution_h=480))
      assert tier == "LOW"
      assert "<720p" in reason


  def test_assign_tier_low_fps() -> None:
      tier, reason = assign_tier(_data(fps_measured=5.0))
      assert tier == "LOW"
      assert "<8fps" in reason


  def test_assign_tier_low_analog_via_encoder() -> None:
      tier, reason = assign_tier(_data(is_analog_via_encoder=True))
      assert tier == "LOW"
      assert "analog" in reason.lower()


  def test_assign_tier_low_focus() -> None:
      tier, reason = assign_tier(_data(focus_score=10.0))
      assert tier == "LOW"
      assert "focus" in reason.lower()


  def test_assign_tier_mid_720p() -> None:
      tier, reason = assign_tier(_data(resolution_h=720))
      assert tier == "MID"


  def test_assign_tier_mid_fps_borderline() -> None:
      tier, reason = assign_tier(_data(fps_measured=10.0))
      assert tier == "MID"


  def test_assign_tier_mid_focus_borderline() -> None:
      tier, reason = assign_tier(_data(focus_score=20.0))
      assert tier == "MID"


  def test_assign_tier_uses_config_thresholds() -> None:
      from vms.config import get_settings
      s = get_settings()
      # Exactly at full threshold — should be FULL
      tier, _ = assign_tier(_data(
          resolution_h=s.profiler_res_full_min_h,
          fps_measured=s.profiler_fps_full_min,
          focus_score=s.profiler_focus_full_min,
      ))
      assert tier == "FULL"


  def test_assign_tier_none_data_returns_full() -> None:
      """When data is missing (None fields), default to FULL (best-effort)."""
      tier, reason = assign_tier(ProfileData())
      assert tier == "FULL"
  ```

- [x] **Step 2: Run tests to verify they fail**

  ```powershell
  pytest tests/profiler/test_tier.py -v
  ```

  Expected: `ERROR` — `ModuleNotFoundError: No module named 'vms.profiler'`

- [x] **Step 3: Create module files**

  Create `vms/profiler/__init__.py` (empty).

  Create `vms/profiler/tier.py`:

  ```python
  """Tier assignment logic: maps measured ProfileData to FULL/MID/LOW."""

  from __future__ import annotations

  from vms.api.schemas import ProfileData
  from vms.config import get_settings


  def assign_tier(data: ProfileData) -> tuple[str, str]:
      """Return (tier, reason) from measured profile data.

      Tier decision order: LOW conditions are checked first (most restrictive).
      If none apply, MID conditions are checked. Otherwise FULL.
      """
      s = get_settings()

      h = data.resolution_h
      fps = data.fps_measured
      focus = data.focus_score

      # -- LOW tier conditions (any single condition = LOW) --
      if h is not None and h < s.profiler_res_mid_min_h:
          return "LOW", f"<720p resolution ({h}p)"
      if fps is not None and fps < s.profiler_fps_mid_min:
          return "LOW", f"<8fps measured ({fps:.1f} fps)"
      if data.is_analog_via_encoder is True:
          return "LOW", "analog-via-encoder deinterlace artifact detected"
      if focus is not None and focus < s.profiler_focus_mid_min:
          return "LOW", f"focus_score<{s.profiler_focus_mid_min} ({focus:.1f})"

      # -- MID tier conditions (any single condition = MID, but no LOW) --
      mid_reasons: list[str] = []
      if h is not None and h < s.profiler_res_full_min_h:
          mid_reasons.append(f"resolution {h}p < {s.profiler_res_full_min_h}p")
      if fps is not None and fps < s.profiler_fps_full_min:
          mid_reasons.append(f"fps {fps:.1f} < {s.profiler_fps_full_min}")
      if focus is not None and focus < s.profiler_focus_full_min:
          mid_reasons.append(f"focus_score {focus:.1f} < {s.profiler_focus_full_min}")
      if mid_reasons:
          return "MID", "; ".join(mid_reasons)

      # -- FULL --
      parts: list[str] = []
      if h is not None:
          parts.append(f">={s.profiler_res_full_min_h}p")
      if fps is not None:
          parts.append(f"fps>={s.profiler_fps_full_min}")
      if focus is not None:
          parts.append(f"focus>={s.profiler_focus_full_min}")
      reason = " AND ".join(parts) if parts else "defaults"
      return "FULL", reason
  ```

- [x] **Step 4: Run tests to verify they pass**

  ```powershell
  pytest tests/profiler/test_tier.py -v
  ```

  Expected: all 10 pass.

- [x] **Step 5: Type-check**

  ```powershell
  mypy vms/profiler/tier.py
  ```

  Expected: `Success: no issues found in 1 source file`

- [x] **Step 6: Commit**

  ```powershell
  git add vms/profiler/__init__.py vms/profiler/tier.py tests/profiler/test_tier.py
  git commit -m "feat: add TierAssigner — maps measured profile to FULL/MID/LOW"
  ```

---

## Task 4: CameraProfiler — RTSP probe

**Files:**
- Create: `vms/profiler/probe.py`
- Create: `tests/profiler/test_probe.py`

- [x] **Step 1: Write failing tests**

  Create `tests/profiler/test_probe.py`:

  ```python
  """CameraProfiler tests — cv2.VideoCapture is mocked."""

  from __future__ import annotations

  from unittest.mock import MagicMock, patch

  import numpy as np
  import pytest

  from vms.profiler.probe import CameraProfiler


  def _make_cap_mock(
      *,
      opened: bool = True,
      width: float = 1920.0,
      height: float = 1080.0,
      fps: float = 25.0,
      fourcc: float = 0.0,
      frame_brightness: int = 128,
  ) -> MagicMock:
      """Build a mock cv2.VideoCapture that returns uniform frames."""
      cap = MagicMock()
      cap.isOpened.return_value = opened
      cap.get.side_effect = lambda prop: {
          3: width,   # CAP_PROP_FRAME_WIDTH
          4: height,  # CAP_PROP_FRAME_HEIGHT
          5: fps,     # CAP_PROP_FPS
          6: fourcc,  # CAP_PROP_FOURCC
      }.get(prop, 0.0)
      frame = np.full((int(height), int(width), 3), frame_brightness, dtype=np.uint8)
      cap.read.return_value = (True, frame)
      return cap


  @patch("vms.profiler.probe.cv2.VideoCapture")
  def test_probe_returns_full_tier_on_1080p_stream(mock_cap_cls: MagicMock) -> None:
      mock_cap_cls.return_value = _make_cap_mock()
      profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
      result = profiler.probe("rtsp://fake/stream")
      assert result.resolution_h == 1080
      assert result.fps_measured is not None
      assert result.suggested_tier == "FULL"


  @patch("vms.profiler.probe.cv2.VideoCapture")
  def test_probe_detects_low_tier_on_480p_stream(mock_cap_cls: MagicMock) -> None:
      mock_cap_cls.return_value = _make_cap_mock(height=480.0, fps=15.0)
      profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
      result = profiler.probe("rtsp://fake/stream")
      assert result.suggested_tier == "LOW"
      assert result.resolution_h == 480


  @patch("vms.profiler.probe.cv2.VideoCapture")
  def test_probe_raises_on_unopened_capture(mock_cap_cls: MagicMock) -> None:
      mock_cap_cls.return_value = _make_cap_mock(opened=False)
      profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
      with pytest.raises(RuntimeError, match="Cannot open RTSP stream"):
          profiler.probe("rtsp://fake/unreachable")


  @patch("vms.profiler.probe.cv2.VideoCapture")
  def test_probe_computes_focus_score(mock_cap_cls: MagicMock) -> None:
      # Uniform frame → Laplacian variance ≈ 0 → LOW focus
      mock_cap_cls.return_value = _make_cap_mock()
      profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
      result = profiler.probe("rtsp://fake/stream")
      assert result.focus_score is not None
      assert result.focus_score >= 0.0


  @patch("vms.profiler.probe.cv2.VideoCapture")
  def test_probe_codec_string_populated(mock_cap_cls: MagicMock) -> None:
      mock_cap_cls.return_value = _make_cap_mock()
      profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
      result = profiler.probe("rtsp://fake/stream")
      assert result.codec is not None


  @patch("vms.profiler.probe.cv2.VideoCapture")
  def test_probe_frame_drop_rate_zero_on_clean_stream(mock_cap_cls: MagicMock) -> None:
      mock_cap_cls.return_value = _make_cap_mock()
      profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
      result = profiler.probe("rtsp://fake/stream")
      assert result.frame_drop_rate == 0.0


  @patch("vms.profiler.probe.cv2.VideoCapture")
  def test_probe_detects_analog_combing_via_alternating_rows(
      mock_cap_cls: MagicMock,
  ) -> None:
      """Frame with strong alternating-row intensity pattern → analog-via-encoder=True."""
      cap = MagicMock()
      cap.isOpened.return_value = True
      cap.get.side_effect = lambda p: {3: 1920.0, 4: 1080.0, 5: 25.0, 6: 0.0}.get(p, 0.0)
      # Deinterlace combing: even rows bright (200), odd rows dark (50)
      frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
      frame[::2] = 200    # even rows bright
      frame[1::2] = 50    # odd rows dark
      cap.read.return_value = (True, frame)
      mock_cap_cls.return_value = cap

      profiler = CameraProfiler(probe_duration_s=0, sample_frames=5)
      result = profiler.probe("rtsp://fake/analog")
      assert result.is_analog_via_encoder is True
  ```

- [x] **Step 2: Run to confirm failure**

  ```powershell
  pytest tests/profiler/test_probe.py -v
  ```

  Expected: `ERROR` — `ModuleNotFoundError: No module named 'vms.profiler.probe'`

- [x] **Step 2b: Verify Pydantic version — affects model_copy call**

  ```powershell
  python -c "import pydantic; print(pydantic.VERSION)"
  ```

  - If **v2.x**: `data.model_copy(update={...})` is correct (used in Step 3).
  - If **v1.x**: change to `data.copy(update={...})` everywhere in `probe.py`.

  This project targets Pydantic v2 (`pydantic-settings==2.2.1` requires it), so `model_copy` is correct. Confirm before proceeding.

- [x] **Step 3: Create `vms/profiler/probe.py`**

  ```python
  """CameraProfiler — RTSP probe that measures stream quality and assigns tier."""

  from __future__ import annotations

  import logging
  import struct
  import time

  import cv2
  import numpy as np

  from vms.api.schemas import ProfileData
  from vms.config import get_settings
  from vms.profiler.tier import assign_tier

  logger = logging.getLogger(__name__)


  class CameraProfiler:
      """Probes an RTSP stream and returns a populated ProfileData."""

      def __init__(
          self,
          probe_duration_s: int | None = None,
          sample_frames: int | None = None,
      ) -> None:
          s = get_settings()
          self._duration = (
              probe_duration_s
              if probe_duration_s is not None
              else s.profiler_probe_duration_s
          )
          self._sample_n = (
              sample_frames
              if sample_frames is not None
              else s.profiler_sample_frames
          )

      def probe(self, rtsp_url: str) -> ProfileData:
          """Open *rtsp_url*, measure for up to _duration seconds, return ProfileData."""
          cap = cv2.VideoCapture(rtsp_url)
          try:
              return self._run(cap, rtsp_url)
          finally:
              cap.release()

      # ------------------------------------------------------------------
      # Internal helpers
      # ------------------------------------------------------------------

      def _run(self, cap: cv2.VideoCapture, url: str) -> ProfileData:
          if not cap.isOpened():
              raise RuntimeError(f"Cannot open RTSP stream: {url}")

          width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
          height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
          declared_fps = cap.get(cv2.CAP_PROP_FPS)
          fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
          codec = self._decode_fourcc(fourcc_int)

          frames: list[np.ndarray] = []
          decoded = 0
          failed = 0
          deadline = time.monotonic() + self._duration if self._duration > 0 else None

          while True:
              if deadline is not None and time.monotonic() >= deadline:
                  break
              ok, frame = cap.read()
              if not ok:
                  failed += 1
                  if failed > 30:
                      break
                  continue
              decoded += 1
              if len(frames) < self._sample_n:
                  frames.append(frame.copy())
              if deadline is None and decoded >= self._sample_n:
                  break

          total = decoded + failed
          drop_rate = (failed / total) if total > 0 else 0.0
          fps_measured = float(decoded / self._duration) if self._duration > 0 else declared_fps

          # Quality metrics from sampled frames
          focus_score: float | None = None
          brightness_mean: float | None = None
          is_analog: bool | None = None

          if frames:
              focus_scores = [
                  float(cv2.Laplacian(cv2.cvtColor(f, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
                  for f in frames
              ]
              focus_score = float(np.mean(focus_scores))

              brightness_vals = [float(np.mean(f)) for f in frames]
              brightness_mean = float(np.mean(brightness_vals))

              is_analog = self._detect_deinterlace_combing(frames)

          shutter_suggestion, shutter_confidence = self._detect_shutter_type(frames)

          data = ProfileData(
              resolution_w=width,
              resolution_h=height,
              fps_measured=fps_measured,
              focus_score=focus_score,
              frame_drop_rate=drop_rate,
              brightness_mean=brightness_mean,
              is_analog_via_encoder=is_analog,
              codec=codec,
              shutter_suggestion=shutter_suggestion,
              shutter_confidence=shutter_confidence,
          )

          tier, tier_reason = assign_tier(data)
          data = data.model_copy(update={"suggested_tier": tier, "tier_reason": tier_reason})
          return data

      @staticmethod
      def _decode_fourcc(fourcc: int) -> str:
          try:
              return struct.pack("<I", fourcc).decode("ascii", errors="replace").strip("\x00")
          except Exception:
              return "UNKN"

      @staticmethod
      def _detect_deinterlace_combing(frames: list[np.ndarray]) -> bool:
          """Return True if alternating-row intensity variance suggests deinterlace combing."""
          if not frames:
              return False
          scores: list[float] = []
          for frame in frames:
              gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
              even_mean = float(gray[::2].mean())
              odd_mean = float(gray[1::2].mean())
              # Strong even/odd row difference indicates combing
              scores.append(abs(even_mean - odd_mean))
          mean_diff = float(np.mean(scores))
          return mean_diff > 20.0  # threshold: 20 brightness units difference

      @staticmethod
      def _detect_shutter_type(
          frames: list[np.ndarray],
      ) -> tuple[str, float]:
          """Estimate shutter type from optical-flow skew variance across frames.

          Returns (suggestion, confidence) where suggestion ∈ {'rolling','global','unknown'}.
          Skew variance > 0.04 → rolling (confidence clamped 60-95%).
          """
          if len(frames) < 4:
              return "unknown", 0.5

          s = get_settings()
          threshold = s.profiler_shutter_skew_threshold

          gray_frames = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames]
          skew_variances: list[float] = []

          for i in range(len(gray_frames) - 1):
              flow = cv2.calcOpticalFlowFarneback(
                  gray_frames[i], gray_frames[i + 1],
                  None, 0.5, 3, 15, 3, 5, 1.2, 0,
              )
              # Horizontal (x) flow variance across rows — rolling shutter causes skew
              h_flow = flow[..., 0]
              row_means = h_flow.mean(axis=1)
              skew_variances.append(float(np.var(row_means)))

          mean_skew = float(np.mean(skew_variances))

          if mean_skew > threshold:
              confidence = min(0.95, max(0.60, 1.0 - mean_skew / (threshold * 2.5)))
              return "rolling", round(confidence, 2)
          elif mean_skew < threshold * 0.5:
              confidence = min(0.95, max(0.60, 1.0 - mean_skew / threshold))
              return "global", round(confidence, 2)
          return "unknown", 0.5
  ```

- [x] **Step 4: Run tests**

  ```powershell
  pytest tests/profiler/test_probe.py -v
  ```

  Expected: all 7 pass. The combing test may be sensitive — adjust the `20.0` threshold in `_detect_deinterlace_combing` if needed so the alternating-row frame (even=200, odd=50 → diff=150) triggers it.

- [x] **Step 5: Type-check**

  ```powershell
  mypy vms/profiler/probe.py
  ```

- [x] **Step 6: Commit**

  ```powershell
  git add vms/profiler/probe.py tests/profiler/test_probe.py
  git commit -m "feat: CameraProfiler — RTSP probe with tier assignment and shutter detection"
  ```

---

## Task 5: SiteReadinessPDF — ReportLab PDF generator

**Files:**
- Create: `vms/profiler/report.py`
- Create: `tests/profiler/test_report.py`

- [x] **Step 1: Write failing tests**

  Create `tests/profiler/test_report.py`:

  ```python
  """Tests for Site Readiness Report PDF generation."""

  from __future__ import annotations

  import pytest
  from vms.api.schemas import ProfileData
  from vms.profiler.report import generate_readiness_report


  def _make_cam_row(
      camera_id: int = 1,
      name: str = "Loading Bay",
      tier: str = "FULL",
      shutter: str = "rolling",
      tier_reason: str = ">=1080p AND fps>=12",
      profile_data: ProfileData | None = None,
  ) -> dict[str, object]:
      return {
          "camera_id": camera_id,
          "name": name,
          "capability_tier": tier,
          "shutter_type": shutter,
          "tier_reason": tier_reason,
          "profile_data": profile_data,
      }


  def test_generate_report_returns_bytes() -> None:
      rows = [_make_cam_row()]
      pdf_bytes = generate_readiness_report(rows)
      assert isinstance(pdf_bytes, bytes)
      assert len(pdf_bytes) > 0


  def test_generate_report_is_valid_pdf() -> None:
      rows = [_make_cam_row()]
      pdf_bytes = generate_readiness_report(rows)
      # PDF magic bytes
      assert pdf_bytes[:4] == b"%PDF"


  def test_generate_report_multiple_cameras() -> None:
      rows = [
          _make_cam_row(camera_id=1, name="Gate 1", tier="FULL"),
          _make_cam_row(camera_id=2, name="Gate 2", tier="MID"),
          _make_cam_row(camera_id=3, name="Warehouse", tier="LOW"),
      ]
      pdf_bytes = generate_readiness_report(rows)
      assert pdf_bytes[:4] == b"%PDF"


  def test_generate_report_with_full_profile_data() -> None:
      pd = ProfileData(
          resolution_w=1920,
          resolution_h=1080,
          fps_measured=25.0,
          focus_score=55.0,
          suggested_tier="FULL",
          tier_reason=">=1080p AND fps>=12 AND focus>=30",
      )
      rows = [_make_cam_row(profile_data=pd)]
      pdf_bytes = generate_readiness_report(rows)
      assert pdf_bytes[:4] == b"%PDF"


  def test_generate_report_empty_camera_list() -> None:
      pdf_bytes = generate_readiness_report([])
      assert isinstance(pdf_bytes, bytes)
      assert pdf_bytes[:4] == b"%PDF"
  ```

- [x] **Step 2: Run to confirm failure**

  ```powershell
  pytest tests/profiler/test_report.py -v
  ```

  Expected: `ERROR` — `ModuleNotFoundError: No module named 'vms.profiler.report'`

- [x] **Step 3: Create `vms/profiler/report.py`**

  ```python
  """Site Readiness Report — generates a one-page PDF per site."""

  from __future__ import annotations

  import io
  from datetime import datetime, timezone
  from typing import Any

  from reportlab.lib import colors
  from reportlab.lib.pagesizes import A4
  from reportlab.lib.styles import getSampleStyleSheet
  from reportlab.lib.units import mm
  from reportlab.platypus import (
      Paragraph,
      SimpleDocTemplate,
      Spacer,
      Table,
      TableStyle,
  )

  from vms.api.schemas import ProfileData

  _TIER_COLOURS = {
      "FULL": colors.HexColor("#28a745"),
      "MID": colors.HexColor("#ffc107"),
      "LOW": colors.HexColor("#dc3545"),
  }


  def generate_readiness_report(
      camera_rows: list[dict[str, Any]],
      site_name: str = "Plant Site",
  ) -> bytes:
      """Return a PDF bytes object — the Site Readiness Report.

      *camera_rows* is a list of dicts with keys:
        camera_id, name, capability_tier, shutter_type, tier_reason, profile_data
      """
      buffer = io.BytesIO()
      doc = SimpleDocTemplate(
          buffer,
          pagesize=A4,
          rightMargin=15 * mm,
          leftMargin=15 * mm,
          topMargin=15 * mm,
          bottomMargin=20 * mm,
      )
      styles = getSampleStyleSheet()
      story: list[Any] = []

      # Title
      now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
      story.append(Paragraph(f"<b>VMS Site Readiness Report</b>", styles["Title"]))
      story.append(Paragraph(f"Site: {site_name} · Generated: {now}", styles["Normal"]))
      story.append(Spacer(1, 8 * mm))

      # Summary counts
      tiers = [r.get("capability_tier", "FULL") for r in camera_rows]
      full_n = tiers.count("FULL")
      mid_n = tiers.count("MID")
      low_n = tiers.count("LOW")
      story.append(
          Paragraph(
              f"<b>Summary:</b> {len(camera_rows)} cameras — "
              f"FULL: {full_n} | MID: {mid_n} | LOW: {low_n}",
              styles["Normal"],
          )
      )
      story.append(Spacer(1, 5 * mm))

      # Per-camera table
      header = ["Camera", "Tier", "Resolution", "FPS", "Focus", "Shutter", "Why"]
      table_data: list[list[str]] = [header]

      for row in camera_rows:
          pd: ProfileData | None = row.get("profile_data")
          resolution = (
              f"{pd.resolution_w}×{pd.resolution_h}"
              if pd and pd.resolution_w and pd.resolution_h
              else "—"
          )
          fps_str = f"{pd.fps_measured:.1f}" if pd and pd.fps_measured is not None else "—"
          focus_str = f"{pd.focus_score:.0f}" if pd and pd.focus_score is not None else "—"
          tier = str(row.get("capability_tier", "FULL"))
          table_data.append(
              [
                  str(row.get("name", "")),
                  tier,
                  resolution,
                  fps_str,
                  focus_str,
                  str(row.get("shutter_type", "unknown")),
                  str(row.get("tier_reason", ""))[:60],
              ]
          )

      col_widths = [45 * mm, 14 * mm, 28 * mm, 14 * mm, 14 * mm, 20 * mm, None]
      tbl = Table(table_data, colWidths=col_widths, repeatRows=1)

      tier_style: list[Any] = [
          ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#343a40")),
          ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
          ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
          ("FONTSIZE", (0, 0), (-1, -1), 8),
          ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
          ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dee2e6")),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
          ("TOPPADDING", (0, 0), (-1, -1), 3),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
      ]
      for i, row in enumerate(camera_rows, start=1):
          tier = str(row.get("capability_tier", "FULL"))
          tier_col = _TIER_COLOURS.get(tier, colors.grey)
          tier_style.append(("BACKGROUND", (1, i), (1, i), tier_col))
          tier_style.append(("TEXTCOLOR", (1, i), (1, i), colors.white))
          tier_style.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))

      tbl.setStyle(TableStyle(tier_style))
      story.append(tbl)

      # Signature block
      story.append(Spacer(1, 15 * mm))
      story.append(
          Paragraph(
              "Customer acceptance: by signing below you confirm this report "
              "reflects the actual camera deployment at your site.",
              styles["Normal"],
          )
      )
      story.append(Spacer(1, 8 * mm))
      sig_data = [
          ["Customer Signature:", "_" * 40, "Date:", "_" * 20],
          ["Print Name:", "_" * 40, "Role:", "_" * 20],
      ]
      sig_tbl = Table(sig_data, colWidths=[35 * mm, 75 * mm, 20 * mm, 45 * mm])
      sig_tbl.setStyle(
          TableStyle(
              [
                  ("FONTSIZE", (0, 0), (-1, -1), 9),
                  ("TOPPADDING", (0, 0), (-1, -1), 5),
                  ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
              ]
          )
      )
      story.append(sig_tbl)

      doc.build(story)
      return buffer.getvalue()
  ```

- [x] **Step 4: Run tests**

  ```powershell
  pytest tests/profiler/test_report.py -v
  ```

  Expected: all 5 pass.

- [x] **Step 5: Type-check**

  ```powershell
  mypy vms/profiler/report.py
  ```

- [x] **Step 6: Commit**

  ```powershell
  git add vms/profiler/report.py tests/profiler/test_report.py
  git commit -m "feat: SiteReadinessPDF — ReportLab A4 per-camera tier report with signature block"
  ```

---

## Task 6: Update POST /cameras/{id}/profile endpoint

The current stub accepts a `ProfileData` body from the client. Replace it with a real profiler invocation that reads the camera's RTSP URL and runs `CameraProfiler`.

**Files:**
- Modify: `vms/api/routes/cameras.py`
- Create/extend: `tests/api/test_cameras_profile.py`

- [x] **Step 1: Write failing test for the updated endpoint**

  Create `tests/api/test_cameras_profile.py`:

  ```python
  """Tests for POST /api/cameras/{id}/profile — real profiler invocation."""

  from __future__ import annotations

  from unittest.mock import MagicMock, patch

  import pytest
  from fastapi.testclient import TestClient
  from sqlalchemy.orm import Session

  from vms.api.schemas import ProfileData


  def _fake_profile_data() -> ProfileData:
      return ProfileData(
          resolution_w=1920,
          resolution_h=1080,
          fps_measured=25.0,
          focus_score=50.0,
          frame_drop_rate=0.0,
          is_analog_via_encoder=False,
          suggested_tier="FULL",
          tier_reason=">=1080p AND fps>=12 AND focus>=30",
          shutter_suggestion="rolling",
          shutter_confidence=0.75,
          codec="H264",
      )


  @pytest.fixture()
  def patched_profiler():
      """Patch CameraProfiler.probe to avoid real RTSP connections in API tests."""
      with patch(
          "vms.api.routes.cameras.CameraProfiler"
      ) as mock_cls:
          inst = MagicMock()
          inst.probe.return_value = _fake_profile_data()
          mock_cls.return_value = inst
          yield mock_cls


  def test_post_profile_triggers_profiler_and_stores_results(
      client: TestClient,
      db: Session,
      patched_profiler: MagicMock,
      admin_headers: dict[str, str],
      sample_camera_id: int,
  ) -> None:
      """POST /api/cameras/{id}/profile runs the profiler and stores results."""
      resp = client.post(
          f"/api/cameras/{sample_camera_id}/profile",
          headers=admin_headers,
      )
      assert resp.status_code == 200
      body = resp.json()
      assert body["capability_tier"] == "FULL"
      assert body["shutter_type"] == "rolling"
      assert body["tier_reason"] is not None
      patched_profiler.assert_called_once()


  def test_post_profile_404_on_unknown_camera(
      client: TestClient,
      admin_headers: dict[str, str],
  ) -> None:
      resp = client.post("/api/cameras/99999/profile", headers=admin_headers)
      assert resp.status_code == 404


  def test_post_profile_rtsp_failure_returns_422(
      client: TestClient,
      admin_headers: dict[str, str],
      sample_camera_id: int,
  ) -> None:
      """If the profiler raises RuntimeError (bad RTSP), the API returns 422."""
      with patch(
          "vms.api.routes.cameras.CameraProfiler"
      ) as mock_cls:
          inst = MagicMock()
          inst.probe.side_effect = RuntimeError("Cannot open RTSP stream")
          mock_cls.return_value = inst
          resp = client.post(
              f"/api/cameras/{sample_camera_id}/profile",
              headers=admin_headers,
          )
          assert resp.status_code == 422
          assert "RTSP probe failed" in resp.json()["detail"]
  ```

  **Note:** These tests depend on pytest fixtures (`client`, `db`, `admin_headers`, `sample_camera_id`). Check `tests/conftest.py` — add `sample_camera_id` fixture if not present.

- [x] **Step 2: Add `sample_camera_id` fixture to conftest if missing**

  Check `tests/conftest.py`. If `sample_camera_id` doesn't exist, add:

  ```python
  @pytest.fixture()
  def sample_camera_id(db: Session) -> int:
      from vms.db.models import Camera
      cam = Camera(name="Test Cam", rtsp_url="rtsp://localhost/test")
      db.add(cam)
      db.commit()
      db.refresh(cam)
      return cam.camera_id
  ```

- [x] **Step 3: Run test to confirm failure**

  ```powershell
  pytest tests/api/test_cameras_profile.py -v 2>&1 | head -30
  ```

  Expected: `FAILED` or `ERROR` (endpoint still returns 202 / takes `ProfileData` body).

- [x] **Step 4: Update `submit_profile` in cameras.py**

  Replace the stub with:

  ```python
  from vms.profiler.probe import CameraProfiler

  @router.post("/cameras/{camera_id}/profile", response_model=ProfileResponse)
  def submit_profile(
      camera_id: int,
      db: Session = Depends(get_db),
      _user: dict[str, Any] = Depends(get_current_user),
  ) -> ProfileResponse:
      cam = _get_camera_or_404(camera_id, db)
      profiler = CameraProfiler()
      try:
          data = profiler.probe(cam.rtsp_url)
      except RuntimeError as exc:
          # 422 not 500: the server is fine; this camera's stream couldn't be probed
          raise HTTPException(
              status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
              detail=f"RTSP probe failed: {exc}",
          )

      cam.profile_data = json.dumps(data.model_dump(exclude_none=False))
      cam.capability_tier = data.suggested_tier or cam.capability_tier
      cam.shutter_type = data.shutter_suggestion or cam.shutter_type
      cam.profiled_at = datetime.now(timezone.utc).replace(tzinfo=None)
      db.commit()
      db.refresh(cam)

      return ProfileResponse(
          camera_id=cam.camera_id,
          profile_data=data,
          profiled_at=cam.profiled_at,
          capability_tier=cam.capability_tier,
          shutter_type=cam.shutter_type,
          tier_reason=data.tier_reason,
      )
  ```

  Remove the old import of `ProfileData` from the function signature.

- [x] **Step 5: Run tests**

  ```powershell
  pytest tests/api/test_cameras_profile.py -v
  ```

  Expected: all 3 pass.

- [x] **Step 6: Type-check + lint**

  ```powershell
  mypy vms/api/routes/cameras.py
  ruff check vms/api/routes/cameras.py
  ```

- [x] **Step 7: Commit**

  ```powershell
  git add vms/api/routes/cameras.py tests/api/test_cameras_profile.py tests/conftest.py
  git commit -m "feat: POST /cameras/{id}/profile triggers CameraProfiler against RTSP stream"
  ```

---

## Task 7: Add GET /api/sites/readiness-report.pdf endpoint

**Files:**
- Modify: `vms/api/routes/cameras.py`
- Extend: `tests/api/test_cameras_profile.py`

- [x] **Step 1: Write failing test**

  Append to `tests/api/test_cameras_profile.py`:

  ```python
  def test_get_readiness_report_returns_pdf(
      client: TestClient,
      admin_headers: dict[str, str],
  ) -> None:
      resp = client.get("/api/sites/readiness-report.pdf", headers=admin_headers)
      assert resp.status_code == 200
      assert resp.headers["content-type"] == "application/pdf"
      assert resp.content[:4] == b"%PDF"


  def test_get_readiness_report_no_cameras_still_returns_pdf(
      client: TestClient,
      admin_headers: dict[str, str],
  ) -> None:
      """Even with no cameras, endpoint must return a valid (empty) PDF."""
      resp = client.get("/api/sites/readiness-report.pdf", headers=admin_headers)
      assert resp.status_code == 200
      assert resp.content[:4] == b"%PDF"
  ```

- [x] **Step 2: Run to confirm failure**

  ```powershell
  pytest tests/api/test_cameras_profile.py::test_get_readiness_report_returns_pdf -v
  ```

  Expected: `FAILED` — 404 (route doesn't exist).

- [x] **Step 3: Add endpoint to cameras.py**

  Add after the `get_profile` endpoint:

  ```python
  from fastapi.responses import Response
  from vms.profiler.report import generate_readiness_report

  @router.get("/sites/readiness-report.pdf")
  def get_site_readiness_report(
      site: str = "Plant Site",
      db: Session = Depends(get_db),
      _user: dict[str, Any] = Depends(get_current_user),
  ) -> Response:
      cameras = db.query(Camera).order_by(Camera.camera_id).all()
      rows = []
      for cam in cameras:
          pd: ProfileData | None = None
          if cam.profile_data:
              try:
                  pd = ProfileData(**json.loads(cam.profile_data))
              except (json.JSONDecodeError, ValueError):
                  pd = None
          rows.append(
              {
                  "camera_id": cam.camera_id,
                  "name": cam.name,
                  "capability_tier": cam.capability_tier,
                  "shutter_type": cam.shutter_type,
                  "tier_reason": pd.tier_reason if pd else None,
                  "profile_data": pd,
              }
          )
      pdf_bytes = generate_readiness_report(rows, site_name=site)
      return Response(
          content=pdf_bytes,
          media_type="application/pdf",
          headers={
              "Content-Disposition": f'attachment; filename="vms-site-readiness-{site}.pdf"'
          },
      )
  ```

- [x] **Step 4: Run tests**

  ```powershell
  pytest tests/api/test_cameras_profile.py -v
  ```

  Expected: all 5 pass.

- [x] **Step 5: Full suite check**

  ```powershell
  pytest -x
  black vms/ tests/
  ruff check vms/ tests/
  mypy vms/
  ```

- [x] **Step 6: Commit**

  ```powershell
  git add vms/api/routes/cameras.py tests/api/test_cameras_profile.py
  git commit -m "feat: GET /api/sites/readiness-report.pdf — per-camera tier PDF using ReportLab"
  ```

---

## Self-review — spec coverage check

Reviewing v2-hardened-design.md §B against this plan:

| Spec requirement | Covered |
|---|---|
| RTSP negotiate (credentials valid, transport) | Task 4 — `cap.isOpened()` check |
| Stream metadata (codec, resolution, fps) | Task 4 — `CAP_PROP_*` reads |
| Live measurement (60s decoded fps, drop rate) | Task 4 — `probe_duration_s` loop |
| Frame-quality sample (Laplacian focus, brightness) | Task 4 — `_run()` sampling |
| Encoder-artifact scan (analog-via-encoder combing) | Task 4 — `_detect_deinterlace_combing()` |
| Night-mode probe (ONVIF IR) | **Deferred — no ONVIF library; tracked in CLAUDE.md §3 Known Gaps for Phase 6** |
| Capability tier FULL/MID/LOW with conditions | Task 3 — `TierAssigner` |
| Shutter type detection (rolling/global/unknown) | Task 4 — `_detect_shutter_type()` |
| Site Readiness Report PDF | Task 5 |
| `POST /api/cameras/{id}/profile` | Task 6 |
| `GET /api/cameras/{id}/profile` | Already existed (Task 2 updates) |
| `GET /api/sites/readiness-report.pdf` | Task 7 |
| DB writes (capability_tier, profile_data, profiled_at, shutter_type) | Task 6 |
| No migration needed — columns exist | Confirmed in pre-task research |
| Tests: mock RTSP, verify tier logic | Tasks 3, 4, 6, 7 |
| `POST /api/cameras/{id}/recalibrate-required` | **Deferred** — tracked in CLAUDE.md §3 Known Gaps (`§H.3`); needs its own plan checkbox; do not implement in this plan |
