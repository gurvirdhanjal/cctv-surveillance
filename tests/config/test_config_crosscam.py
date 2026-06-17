"""Cross-camera accuracy config defaults (Phase 3 crosscam-accuracy plan, Task 1)."""

from vms.config import Settings


def test_settings_tracker_buffer_frames_default_matches_botsort_yaml() -> None:
    s = Settings()
    assert s.tracker_buffer_frames == 90


def test_settings_predictor_history_len_has_conservative_default() -> None:
    s = Settings()
    assert s.reid_predictor_history_len == 8


def test_settings_predictor_max_predict_gap_ms_default() -> None:
    s = Settings()
    assert s.reid_predictor_max_predict_gap_ms == 900_000


def test_settings_headcount_overlap_dedup_disabled_by_default() -> None:
    # No overlap declared in default topology -> uncertain_count must stay computable as 0.
    s = Settings()
    assert s.reid_camera_topology_json == "{}"
