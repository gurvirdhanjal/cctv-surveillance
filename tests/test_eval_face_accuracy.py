"""Regression test: face pipeline accuracy against the employees fixture dataset.

Marked @pytest.mark.eval — excluded from the normal test run.
Run explicitly with:
    pytest -m eval -v
    pytest tests/test_eval_face_accuracy.py -v

Requires:
  - models/scrfd_2.5g.onnx
  - models/adaface_ir50.onnx
  - employees/  (7 persons x 6 images each)

Pass criteria (mirrors scripts/eval_face_accuracy.py thresholds):
  - Rank-1 accuracy         >= 90%   (at least 90% of detected probes match correctly)
  - Max impostor similarity  < 0.72  (no cross-person pair reaches the live threshold)
  - Min genuine similarity  >= 0.62  (all same-person pairs clear the soft-match floor)
  - Detection rate          >= 80%   (at least 80% of probe images yield a detectable face)
"""

from __future__ import annotations

import pytest


@pytest.mark.eval
def test_face_pipeline_accuracy() -> None:
    """End-to-end: enrol employees/*/01.jpg, probe 02–06, assert accuracy thresholds."""
    from scripts.eval_face_accuracy import (
        DETECTION_RATE_MIN,
        MAX_IMPOSTOR_SIM,
        MIN_GENUINE_SIM,
        RANK1_MIN,
        run_eval,
    )

    result = run_eval(
        dataset_dir="employees",
        detector_path="models/scrfd_2.5g.onnx",
        embedder_path="models/adaface_ir50.onnx",
        verbose=True,
    )

    assert result.n_enrolled >= 1, "No persons could be enrolled — check model paths"

    assert result.detection_rate >= DETECTION_RATE_MIN, (
        f"Detection rate {result.detection_rate:.1%} is below {DETECTION_RATE_MIN:.0%}. "
        f"Missed images: {[p.true_person + '/' + p.image_name for p in result.probes if p.status == 'no_face']}"
    )

    assert result.rank1_accuracy >= RANK1_MIN, (
        f"Rank-1 accuracy {result.rank1_accuracy:.1%} is below {RANK1_MIN:.0%}. "
        f"Wrong predictions: {[(p.true_person, p.predicted_person, round(p.top_sim or 0, 4)) for p in result.probes if p.status == 'ok' and not p.correct]}"
    )

    assert result.max_impostor < MAX_IMPOSTOR_SIM, (
        f"An impostor pair reached similarity {result.max_impostor:.4f} >= "
        f"live threshold {MAX_IMPOSTOR_SIM}. This would cause a false identity match in production."
    )

    if result.genuine_sims:
        assert result.min_genuine >= MIN_GENUINE_SIM, (
            f"A genuine pair dipped to {result.min_genuine:.4f} < soft floor {MIN_GENUINE_SIM}. "
            f"This person would fall into the soft-match zone (see §P.1.1) and require operator confirmation."
        )
