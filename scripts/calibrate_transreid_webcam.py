"""Webcam-based threshold calibration for TransReID body Re-ID.

Collects labeled body crop embeddings from a live webcam, then computes
same-person vs different-person cosine similarity distributions to recommend
reid_body_confirmed_sim and reid_body_cross_cam_sim thresholds.

Prerequisites:
    python scripts/export_transreid_onnx.py    # produces models/transreid_body_msmt17.onnx

Usage:
    python scripts/calibrate_transreid_webcam.py
    python scripts/calibrate_transreid_webcam.py --camera 1 --model models/transreid_body_msmt17.onnx

Controls (shown in live window):
    1-9   : select active person ID
    SPACE : capture current frame for active person
    D     : done — stop capturing, run analysis
    Q     : quit without analysis

Recommended session:
    - Two people minimum; three is better for cross-person variance
    - 8-15 captures per person, across slightly different poses/distances
    - Keep each person in the center of the frame, roughly waist-up visible

Output:
    Prints threshold recommendations.
    Saves labeled embeddings to data/webcam_calibration/embeddings.npz for re-analysis.

IMPORTANT: This script only REPORTS recommendations.
    Changing reid_body_confirmed_sim requires a mandatory /advisor session (CLAUDE.md §0.5).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import cv2
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "models/transreid_body_msmt17.onnx"
_DEFAULT_CAMERA = 0
_EMBED_DIM = 768
_INPUT_H = 384
_INPUT_W = 128
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Crop region: center 60% of width, full height.
# Keeps the person roughly centred and reduces background noise.
_CROP_W_FRAC = 0.60
_CROP_H_FRAC = 1.00


def _load_model(model_path: str) -> "ort.InferenceSession":  # type: ignore[name-defined]
    try:
        import onnxruntime as ort
    except ImportError:
        sys.exit("onnxruntime not installed. pip install onnxruntime")

    if not os.path.exists(model_path):
        sys.exit(
            f"ONNX model not found: {model_path}\n"
            "Export first: python scripts/export_transreid_onnx.py"
        )
    sess = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
    logger.info("Loaded %s", model_path)
    return sess


def _preprocess(crop_bgr: np.ndarray) -> np.ndarray:  # type: ignore[type-arg]
    resized = cv2.resize(crop_bgr, (_INPUT_W, _INPUT_H), interpolation=cv2.INTER_LANCZOS4)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    rgb = (rgb - _IMAGENET_MEAN) / _IMAGENET_STD
    return np.transpose(rgb, (2, 0, 1))[None].astype(np.float32)  # (1,3,H,W)


def _embed(sess: "ort.InferenceSession", crop_bgr: np.ndarray) -> np.ndarray:  # type: ignore[name-defined, type-arg]
    blob = _preprocess(crop_bgr)
    input_name = sess.get_inputs()[0].name
    raw = sess.run(None, {input_name: blob})[0][0]  # (768,)
    norm = np.linalg.norm(raw)
    if norm > 1e-8:
        raw = raw / norm
    return raw.astype(np.float32)


def _extract_body_crop(frame: np.ndarray) -> np.ndarray:  # type: ignore[type-arg]
    """Return center-width crop of the frame as the body ROI."""
    h, w = frame.shape[:2]
    cw = int(w * _CROP_W_FRAC)
    ch = int(h * _CROP_H_FRAC)
    x1 = (w - cw) // 2
    y1 = (h - ch) // 2
    return frame[y1 : y1 + ch, x1 : x1 + cw]


def _draw_overlay(
    frame: np.ndarray,  # type: ignore[type-arg]
    active_person: int,
    counts: dict[int, int],
    capturing: bool,
) -> np.ndarray:  # type: ignore[type-arg]
    out = frame.copy()
    h, w = out.shape[:2]

    # Crop box
    cw = int(w * _CROP_W_FRAC)
    x1 = (w - cw) // 2
    cv2.rectangle(out, (x1, 0), (x1 + cw, h), (0, 255, 0), 2)

    # Instructions
    lines = [
        f"Active person: {active_person}  (press 1-9 to switch)",
        "SPACE: capture  D: done  Q: quit",
        "Counts: " + "  ".join(f"P{p}:{c}" for p, c in sorted(counts.items())),
    ]
    for i, line in enumerate(lines):
        cv2.putText(out, line, (10, 25 + i * 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 2)

    if capturing:
        cv2.putText(out, "CAPTURED", (w // 2 - 70, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 200, 0), 3)

    return out


def _collect(camera: int | str, sess: "ort.InferenceSession") -> tuple[np.ndarray, list[int]]:  # type: ignore[name-defined]
    """Open webcam or RTSP stream and interactively collect labeled embeddings.

    Returns:
        embeddings: (N, 768) float32 array
        labels: list of N person IDs (1-indexed ints)
    """
    cap = cv2.VideoCapture(camera)
    if not cap.isOpened():
        sys.exit(f"Cannot open video source: {camera}")

    embeddings: list[np.ndarray] = []  # type: ignore[type-arg]
    labels: list[int] = []
    counts: dict[int, int] = {}
    active_person = 1
    flash_frames = 0

    logger.info("Webcam open. Controls: 1-9=person, SPACE=capture, D=done, Q=quit")

    while True:
        ret, frame = cap.read()
        if not ret:
            logger.warning("Frame read failed — retrying")
            continue

        flash = flash_frames > 0
        if flash_frames > 0:
            flash_frames -= 1

        display = _draw_overlay(frame, active_person, counts, flash)
        cv2.imshow("TransReID Calibration", display)

        key = cv2.waitKey(30) & 0xFF

        if key == ord("q"):
            logger.info("Quit without analysis.")
            cap.release()
            cv2.destroyAllWindows()
            sys.exit(0)

        elif key == ord("d"):
            break

        elif ord("1") <= key <= ord("9"):
            active_person = key - ord("0")

        elif key == ord(" "):
            crop = _extract_body_crop(frame)
            emb = _embed(sess, crop)
            embeddings.append(emb)
            labels.append(active_person)
            counts[active_person] = counts.get(active_person, 0) + 1
            flash_frames = 8
            logger.info("Captured person %d  (total: %d)", active_person, len(labels))

    cap.release()
    cv2.destroyAllWindows()
    return np.array(embeddings, dtype=np.float32), labels


def _analyze(embeddings: np.ndarray, labels: list[int]) -> None:  # type: ignore[type-arg]
    """Compute same-person / different-person similarity distributions and print recommendations."""
    persons = sorted(set(labels))
    n = len(labels)

    if n < 4:
        print("Need at least 4 captures to analyze. Collect more data.")
        return

    if len(persons) < 2:
        print("Need at least 2 different people to compute cross-person similarities.")
        return

    same_sims: list[float] = []
    diff_sims: list[float] = []

    for i in range(n):
        for j in range(i + 1, n):
            sim = float(np.dot(embeddings[i], embeddings[j]))
            if labels[i] == labels[j]:
                same_sims.append(sim)
            else:
                diff_sims.append(sim)

    if not same_sims:
        print("No same-person pairs found. Capture multiple frames per person.")
        return

    same = np.array(same_sims)
    diff = np.array(diff_sims) if diff_sims else np.array([0.0])

    print("\n" + "=" * 60)
    print("TRANSREID WEBCAM CALIBRATION RESULTS")
    print("=" * 60)
    print(f"\nCaptures: {n} total  |  Persons: {', '.join(f'P{p}' for p in persons)}")
    print(f"Same-person pairs:  {len(same_sims)}")
    print(f"Diff-person pairs:  {len(diff_sims)}\n")

    print("Same-person cosine similarity:")
    print(f"  min={same.min():.3f}  p5={np.percentile(same,5):.3f}  "
          f"median={np.median(same):.3f}  p95={np.percentile(same,95):.3f}  max={same.max():.3f}")

    if diff_sims:
        print("\nDiff-person cosine similarity:")
        print(f"  min={diff.min():.3f}  p50={np.median(diff):.3f}  "
              f"p95={np.percentile(diff,95):.3f}  p99={np.percentile(diff,99):.3f}  max={diff.max():.3f}")

    # Conservative threshold: same_p5 rounded down slightly, must be above diff_p99
    same_p5 = float(np.percentile(same, 5))
    diff_p99 = float(np.percentile(diff, 99)) if diff_sims else 0.0
    diff_p95 = float(np.percentile(diff, 95)) if diff_sims else 0.0

    conservative = round(max(same_p5 - 0.05, diff_p99 + 0.01), 2)
    balanced = round((same_p5 + diff_p99) / 2, 2)
    cross_cam = round(conservative + 0.05, 2)  # slightly looser for unconfirmed tracks

    print("\n--- THRESHOLD RECOMMENDATIONS ---")
    print(f"  Conservative (95% recall):  reid_body_confirmed_sim = {conservative:.2f}")
    print(f"  Balanced (99% FP guard):    reid_body_confirmed_sim = {balanced:.2f}")
    print(f"  Cross-cam (unconfirmed):    reid_body_cross_cam_sim = {cross_cam:.2f}")

    if same_p5 <= diff_p99:
        print("\n  WARNING: Same-person p5 <= diff-person p99.")
        print("  The embedding distributions overlap significantly.")
        print("  Collect more diverse same-person captures (different poses, distances, lighting).")
        print("  Current thresholds may produce high false-positive rate.")
    else:
        gap = same_p5 - diff_p99
        print(f"\n  Distribution gap (same_p5 - diff_p99): {gap:.3f}")
        if gap > 0.15:
            print("  Good separation — confident threshold recommendation.")
        elif gap > 0.05:
            print("  Moderate separation — acceptable for initial deployment.")
        else:
            print("  Narrow gap — collect more data before tightening thresholds.")

    print("\n  Current values in config:")
    print("    reid_body_confirmed_sim = 0.51  (OSNet-calibrated — NOT valid for TransReID)")
    print("    reid_body_cross_cam_sim = 0.56  (OSNet-calibrated — NOT valid for TransReID)")
    print("\n  MANDATORY: Run /advisor before changing reid_body_confirmed_sim (CLAUDE.md §0.5)")
    print("=" * 60)


def _save(
    embeddings: np.ndarray,  # type: ignore[type-arg]
    labels: list[int],
    out_dir: str = "data/webcam_calibration",
) -> None:
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    out_path = Path(out_dir) / "embeddings.npz"
    np.savez(str(out_path), embeddings=embeddings, labels=np.array(labels, dtype=np.int32))
    logger.info("Saved embeddings to %s", out_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--camera", type=int, default=_DEFAULT_CAMERA, help="cv2.VideoCapture index (default 0)")
    parser.add_argument("--rtsp-url", default=None, metavar="URL",
        help="RTSP stream URL to use instead of webcam (e.g. rtsp://admin:...@172.16.2.105:554/...)")
    parser.add_argument("--model", default=_DEFAULT_MODEL, help="TransReID ONNX path")
    parser.add_argument(
        "--from-saved",
        metavar="PATH",
        help="Skip capture; re-analyze a saved embeddings.npz",
    )
    args = parser.parse_args()

    if args.from_saved:
        data = np.load(args.from_saved)
        embeddings = data["embeddings"]
        labels = list(map(int, data["labels"]))
        logger.info("Loaded %d embeddings from %s", len(labels), args.from_saved)
        _analyze(embeddings, labels)
        return

    source: int | str = args.rtsp_url if args.rtsp_url else args.camera
    if args.rtsp_url:
        os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

    sess = _load_model(args.model)
    embeddings, labels = _collect(source, sess)

    if len(labels) == 0:
        print("No captures recorded.")
        return

    _save(embeddings, labels)
    _analyze(embeddings, labels)


if __name__ == "__main__":
    main()
