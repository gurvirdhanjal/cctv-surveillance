"""Tests for multi_cam_pipeline_test calibration stats.

Covers the three changes made for measurement hardening:
  - Percentile output (p5/p25/p50/p75/p95) instead of avg/min/max
  - Body acceptance rate (embedded / attempts %)
  - Body quality hint based on p25 with n>=10 gate, not raw min
"""

from __future__ import annotations

import io
import os
import sys
from collections import deque
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace

# The script calls os.environ.setdefault() and load_dotenv() at module level,
# which mutates the process environment with test-mode / .env values. Snapshot
# the full environment before the import and restore it after so other test
# modules (test_config.py, test_inference_detector.py) see clean defaults.
_env_before = dict(os.environ)

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import multi_cam_pipeline_test as mct  # noqa: E402 — sys.path must be set first

for _k in list(os.environ.keys()):
    if _k not in _env_before:
        del os.environ[_k]
    elif os.environ[_k] != _env_before[_k]:
        os.environ[_k] = _env_before[_k]
for _k, _v in _env_before.items():
    if _k not in os.environ:
        os.environ[_k] = _v


def _make_settings(**overrides: float) -> SimpleNamespace:
    defaults = dict(
        min_blur=8.0,
        reid_face_quality_floor=0.0,
        reid_body_quality_floor=0.0,
        torso_kp_conf_threshold=0.30,
        torso_crop_pad_fraction=0.20,
        reid_body_confirmed_sim=0.65,
        reid_body_cross_cam_sim=0.70,
        reid_enroll_dedup_sim=0.95,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _capture(stats_list: list, state: mct.PipelineState | None = None) -> str:
    if state is None:
        state = mct.PipelineState()
    buf = io.StringIO()
    with redirect_stdout(buf):
        mct._print_calibration_stats(stats_list, state, _make_settings())
    return buf.getvalue()


def _make_stats(
    camera_id: int = 141,
    label: str = "Gate 4",
    body_q: list[float] | None = None,
    face_q: list[float] | None = None,
    attempts: int = 0,
    embedded: int = 0,
    faces_detected: int = 0,
    faces_embedded: int = 0,
    faces_rejected: int = 0,
) -> mct.CameraStats:
    s = mct.CameraStats(camera_id, label)
    if body_q is not None:
        s.body_quality_norms = deque(body_q, maxlen=200)
        s.total_body_attempts = attempts or len(body_q)
        s.total_body_embedded = embedded if embedded else len(body_q)
    if face_q is not None:
        s.face_quality_norms = deque(face_q, maxlen=200)
        s.total_faces_detected = faces_detected or len(face_q)
        s.total_faces_embedded = faces_embedded or len(face_q)
        s.total_faces_rejected = faces_rejected
    return s


class TestCameraStatsStructure:
    def test_total_body_embedded_field_exists(self) -> None:
        s = mct.CameraStats(105, "Back Gate")
        assert hasattr(s, "total_body_embedded")

    def test_total_body_embedded_starts_at_zero(self) -> None:
        s = mct.CameraStats(105, "Back Gate")
        assert s.total_body_embedded == 0

    def test_total_body_embedded_independent_of_attempts(self) -> None:
        s = mct.CameraStats(105, "Back Gate")
        s.total_body_attempts = 50
        assert s.total_body_embedded == 0


class TestPercentileOutput:
    def test_body_quality_shows_p5_p25_p50_p75_p95(self) -> None:
        values = [float(v) for v in range(100, 4100, 20)]  # 200 values
        out = _capture([_make_stats(body_q=values)])
        assert "p5=" in out
        assert "p25=" in out
        assert "p50=" in out
        assert "p75=" in out
        assert "p95=" in out

    def test_body_quality_does_not_show_avg_or_min(self) -> None:
        values = [float(v) for v in range(100, 4100, 20)]
        out = _capture([_make_stats(body_q=values)])
        bq_line = next(ln for ln in out.splitlines() if "Body  Bq" in ln)
        assert "avg=" not in bq_line
        assert "min=" not in bq_line
        assert "max=" not in bq_line

    def test_body_quality_p50_value_is_accurate(self) -> None:
        # 200 values from 0..199 → p50 ≈ 99.5
        values = [float(v) for v in range(200)]
        out = _capture([_make_stats(body_q=values)])
        assert "p50=99" in out or "p50=100" in out

    def test_face_quality_shows_percentiles(self) -> None:
        fq = [float(v) for v in range(10, 30)]  # 20 samples
        out = _capture([_make_stats(face_q=fq)])
        fq_line = next(ln for ln in out.splitlines() if "Face  Fq" in ln)
        assert "p5=" in fq_line
        assert "p50=" in fq_line
        assert "p95=" in fq_line

    def test_no_data_shown_when_deques_empty(self) -> None:
        s = mct.CameraStats(105, "Back Gate")
        out = _capture([s])
        bq_line = next(ln for ln in out.splitlines() if "Body  Bq" in ln)
        fq_line = next(ln for ln in out.splitlines() if "Face  Fq" in ln)
        assert "no data yet" in bq_line
        assert "no data yet" in fq_line

    def test_sample_count_n_shown_in_body_output(self) -> None:
        values = [1000.0] * 42
        out = _capture([_make_stats(body_q=values)])
        assert "n=42" in out


class TestBodyAcceptanceRate:
    def test_full_acceptance_shows_100_percent(self) -> None:
        s = _make_stats(body_q=[1500.0] * 42, attempts=42, embedded=42)
        out = _capture([s])
        body_line = next(ln for ln in out.splitlines() if "Body     :" in ln)
        assert "embedded=42" in body_line
        assert "100.0%" in body_line

    def test_partial_acceptance_shows_correct_percent(self) -> None:
        s = mct.CameraStats(141, "Gate 4")
        s.total_body_attempts = 100
        s.total_body_embedded = 75
        out = _capture([s])
        body_line = next(ln for ln in out.splitlines() if "Body     :" in ln)
        assert "embedded=75" in body_line
        assert "75.0%" in body_line

    def test_zero_attempts_shows_zero_percent(self) -> None:
        s = mct.CameraStats(105, "Back Gate")
        out = _capture([s])
        body_line = next(ln for ln in out.splitlines() if "Body     :" in ln)
        assert "embedded=0" in body_line
        assert "0.0%" in body_line

    def test_acceptance_rate_shown_alongside_crops_count(self) -> None:
        s = mct.CameraStats(141, "Gate 4")
        s.total_body_attempts = 200
        s.total_body_embedded = 180
        out = _capture([s])
        body_line = next(ln for ln in out.splitlines() if "Body     :" in ln)
        assert "crops=200" in body_line
        assert "embedded=180" in body_line


class TestBodyQualityHint:
    def test_hint_fires_when_p25_below_200_and_n_is_10(self) -> None:
        # All values = 1.0 → p25 = 1.0, n = 10
        s = _make_stats(body_q=[1.0] * 10)
        out = _capture([s])
        assert "bottom quartile" in out
        assert f"CAM{s.camera_id}" in out

    def test_hint_suppressed_when_n_below_10(self) -> None:
        # Only 9 samples — insufficient for reliable p25
        s = _make_stats(body_q=[1.0] * 9)
        out = _capture([s])
        assert "bottom quartile" not in out

    def test_hint_suppressed_when_p25_at_or_above_200(self) -> None:
        # Healthy camera: p25 well above 200
        s = _make_stats(body_q=[1500.0] * 50)
        out = _capture([s])
        assert "bottom quartile" not in out

    def test_hint_does_not_fire_on_single_outlier(self) -> None:
        # One blurry crop (min=5) in a healthy camera — old code would fire; new code must not
        values = [1500.0] * 199 + [5.0]
        s = _make_stats(body_q=values)
        out = _capture([s])
        assert "bottom quartile" not in out

    def test_hint_reports_p25_value(self) -> None:
        # p25 of [1]*200 = 1.0
        s = _make_stats(body_q=[1.0] * 200)
        out = _capture([s])
        assert "p25=1" in out
