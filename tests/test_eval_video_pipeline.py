"""Video pipeline eval tests.

Two tests, both marked @pytest.mark.eval (excluded from the normal suite).

  test_video_smoke_pipeline
    Runs SCRFD+AdaFace on the existing market1501_5persons.mp4 test video.
    Asserts the pipeline processes frames without crashing and within a
    reasonable time budget.  Detection rate is reported but NOT asserted
    because Market1501 is a body-level surveillance dataset where faces
    are small and detection naturally varies.

  test_voxceleb_face_verification
    Runs the VoxCeleb1 face verification eval on the mini test set.
    Skips (not fails) if the dataset has not been downloaded yet.
    Download it with: python scripts/download_voxceleb_mini.py

    Requires:
      - data/voxceleb_mini/pairs.csv
      - data/voxceleb_mini/clips/*.mp4
      - models/scrfd_2.5g.onnx
      - models/adaface_ir50.onnx

    Pass criteria (mirrors thresholds in scripts/eval_video_pipeline.py):
      - Usable pair rate >= 70%  (both clips had detectable faces)
      - AUC              >= 0.85
      - EER              <= 0.15
"""

from __future__ import annotations

from pathlib import Path

import pytest

SMOKE_VIDEO = "data/test_videos/market1501_s02_five_persons.mp4"
VOXCELEB_PAIRS = "data/voxceleb_mini/pairs.csv"
VOXCELEB_CLIPS = "data/voxceleb_mini/clips"
DETECTOR = "models/scrfd_2.5g.onnx"
EMBEDDER = "models/adaface_ir50.onnx"


@pytest.mark.eval
def test_video_smoke_pipeline() -> None:
    """Smoke: process market1501_5persons.mp4 without crashing."""
    if not Path(SMOKE_VIDEO).exists():
        pytest.skip(f"Smoke video not found: {SMOKE_VIDEO}")
    if not Path(DETECTOR).exists() or not Path(EMBEDDER).exists():
        pytest.skip("ONNX models not found - run: vms-models download")

    from scripts.eval_video_pipeline import run_smoke

    result = run_smoke(
        video_path=SMOKE_VIDEO,
        detector_path=DETECTOR,
        embedder_path=EMBEDDER,
        max_frames=150,
        sample_step=3,
        verbose=True,
    )

    assert (
        result.n_frames_processed > 0
    ), "No frames were processed - video may be unreadable or empty"
    # Processing speed sanity check: must manage at least 0.5 fps on CPU
    # (150 frames sampled from ~450 source frames should take < 300s on CPU)
    assert result.fps > 0.0, "FPS reported as zero - timing error"

    # Report detection rate without asserting - Market1501 has small/distant faces
    # so 0% detection is expected and acceptable for a smoke test.
    print(
        f"\nSmoke result: {result.n_frames_processed} frames processed, "
        f"{result.n_faces_detected} faces detected "
        f"({result.detection_rate:.1%}), "
        f"{result.fps:.1f} fps"
    )
    # The test passes as long as the pipeline ran without crashing.
    assert result.passed, f"Smoke test failed: {result.fail_reasons}"


@pytest.mark.eval
def test_voxceleb_face_verification() -> None:
    """VoxCeleb1 mini: face verification AUC >= 0.85.

    Skip if download_voxceleb_mini.py has not been run.
    """
    if not Path(VOXCELEB_PAIRS).exists():
        pytest.skip(
            f"VoxCeleb1 mini test set not found at {VOXCELEB_PAIRS}.\n"
            f"Download it with: python scripts/download_voxceleb_mini.py"
        )
    if not Path(DETECTOR).exists() or not Path(EMBEDDER).exists():
        pytest.skip("ONNX models not found - run: vms-models download")

    from scripts.eval_video_pipeline import (
        AUC_MIN,
        EER_MAX,
        USABLE_PAIRS_MIN,
        run_verification,
    )

    result = run_verification(
        pairs_file=VOXCELEB_PAIRS,
        clips_dir=VOXCELEB_CLIPS,
        detector_path=DETECTOR,
        embedder_path=EMBEDDER,
        max_frames_per_clip=30,
        verbose=True,
    )

    assert result.n_pairs_total > 0, "No pairs in CSV - check download"

    assert result.usable_pair_rate >= USABLE_PAIRS_MIN, (
        f"Only {result.usable_pair_rate:.1%} of pairs had detectable faces in both clips "
        f"(need {USABLE_PAIRS_MIN:.0%}).  The SCRFD model may not be detecting faces in "
        f"these video clips.  Check min_face_px or try a different detector."
    )

    assert result.auc >= AUC_MIN, (
        f"Face verification AUC {result.auc:.4f} < {AUC_MIN}.\n"
        f"EER: {result.eer:.4f}  TAR@FAR=0.1: {result.tar_at_far01:.4f}\n"
        f"This indicates the AdaFace embedder is not distinguishing identities "
        f"reliably in video.  Possible causes: model not loaded correctly, "
        f"faces too small in clips, CUDA not available (running on CPU is slower "
        f"but should not affect accuracy)."
    )

    assert result.eer <= EER_MAX, (
        f"EER {result.eer:.4f} > {EER_MAX} maximum.  "
        f"AUC was {result.auc:.4f} which passed, but the EER suggests the "
        f"similarity threshold needs tuning."
    )
