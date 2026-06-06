"""Video face pipeline eval - smoke test and VoxCeleb1 face verification.

Two modes:

  smoke       Run SCRFD+AdaFace on a single video.  Reports detection rate,
              embedding consistency, and processing FPS.  No accuracy labels
              needed - just confirms the pipeline handles real video frames.

  verification  Read a VoxCeleb1-format pairs CSV (label,clip1,clip2), embed
                each clip by averaging face embeddings across sampled frames,
                compute cosine similarity per pair, report AUC/EER.

Usage:
    # Smoke on an existing test video
    python scripts/eval_video_pipeline.py --video data/test_videos/market1501_5persons.mp4

    # VoxCeleb1 face verification (download pairs first)
    python scripts/eval_video_pipeline.py --pairs data/voxceleb_mini/pairs.csv

    # Custom model paths
    python scripts/eval_video_pipeline.py \\
        --video clip.mp4 \\
        --detector models/scrfd_2.5g.onnx \\
        --embedder models/adaface_ir50.onnx

Download the VoxCeleb1 mini test set with:
    python scripts/download_voxceleb_mini.py
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pass/fail thresholds
# ---------------------------------------------------------------------------

AUC_MIN = 0.85           # Area Under ROC Curve - random = 0.5, perfect = 1.0
EER_MAX = 0.15           # Equal Error Rate - lower is better
USABLE_PAIRS_MIN = 0.70  # fraction of pairs where both clips yield face embeddings

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ClipResult:
    path: str
    n_frames_sampled: int
    n_faces_detected: int
    mean_embedding: np.ndarray | None  # L2-normalised mean, or None if no faces
    detection_rate: float
    intra_sim: float | None  # mean pairwise cosine sim between same-clip embeddings


@dataclass
class PairResult:
    label: int          # 1 = same person, 0 = different
    clip1_path: str
    clip2_path: str
    similarity: float | None  # None if either clip has no detected face
    clip1_det_rate: float
    clip2_det_rate: float


@dataclass
class VideoEvalResult:
    mode: str           # "smoke" or "verification"

    # Smoke fields (set by finalise_smoke)
    n_frames_processed: int = 0
    n_faces_detected: int = 0
    detection_rate: float = 0.0
    fps: float = 0.0
    mean_intra_sim: float = 0.0  # embedding consistency across frames

    # Verification fields (set by finalise_verification)
    n_pairs_total: int = 0
    n_pairs_usable: int = 0
    auc: float = 0.0
    eer: float = 0.0
    tar_at_far01: float = 0.0
    usable_pair_rate: float = 0.0
    pairs: list[PairResult] = field(default_factory=list)

    passed: bool = False
    fail_reasons: list[str] = field(default_factory=list)

    def finalise_smoke(self, elapsed: float) -> None:
        self.fps = self.n_frames_processed / elapsed if elapsed > 0 else 0.0
        self.detection_rate = (
            self.n_faces_detected / self.n_frames_processed
            if self.n_frames_processed > 0
            else 0.0
        )
        self.fail_reasons = []
        if self.n_frames_processed == 0:
            self.fail_reasons.append("No frames were processed from the video")
        self.passed = len(self.fail_reasons) == 0

    def finalise_verification(self) -> None:
        usable = [p for p in self.pairs if p.similarity is not None]
        self.n_pairs_usable = len(usable)
        self.usable_pair_rate = self.n_pairs_usable / self.n_pairs_total if self.n_pairs_total else 0.0

        labels = [p.label for p in usable]
        scores = [p.similarity for p in usable]  # type: ignore[misc]

        if len(usable) < 10:
            self.auc = 0.0
            self.eer = 1.0
            self.tar_at_far01 = 0.0
        else:
            self.auc = _auc(labels, scores)
            self.eer = _eer(labels, scores)
            self.tar_at_far01 = _tar_at_far(labels, scores, target_far=0.1)

        self.fail_reasons = []
        if self.usable_pair_rate < USABLE_PAIRS_MIN:
            self.fail_reasons.append(
                f"Only {self.usable_pair_rate:.1%} of pairs had detectable faces in both clips"
                f" (need {USABLE_PAIRS_MIN:.0%})"
            )
        if self.auc < AUC_MIN:
            self.fail_reasons.append(
                f"AUC {self.auc:.4f} < {AUC_MIN} required"
            )
        if self.eer > EER_MAX:
            self.fail_reasons.append(
                f"EER {self.eer:.4f} > {EER_MAX} maximum"
            )
        self.passed = len(self.fail_reasons) == 0


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _embed_frame(
    frame: np.ndarray,  # type: ignore[type-arg]
    detector: Any,
    embedder: Any,
    min_face_px: int = 20,
) -> np.ndarray | None:  # type: ignore[type-arg]
    """Detect the largest face in a frame and return its L2-normalised embedding."""
    faces = detector.detect(frame)
    if not faces:
        return None
    best = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
    x1, y1, x2, y2 = best.bbox
    if (x2 - x1) < min_face_px or (y2 - y1) < min_face_px:
        return None
    result = embedder.embed(best, frame)
    if result is None or not result.embedding:
        return None
    emb = np.array(result.embedding, dtype=np.float32)
    norm = float(np.linalg.norm(emb))
    return emb / norm if norm > 0 else emb


def _embed_clip(
    video_path: Path,
    detector: Any,
    embedder: Any,
    max_frames: int = 30,
    sample_step: int = 5,
) -> ClipResult:
    """Sample frames from a video clip and compute the mean face embedding."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        logger.warning("Cannot open video: %s", video_path)
        return ClipResult(str(video_path), 0, 0, None, 0.0, None)

    embeddings: list[np.ndarray] = []  # type: ignore[type-arg]
    n_sampled = 0
    frame_idx = 0

    while n_sampled < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        if frame_idx % sample_step != 0:
            continue
        n_sampled += 1
        emb = _embed_frame(frame, detector, embedder)
        if emb is not None:
            embeddings.append(emb)

    cap.release()

    detection_rate = len(embeddings) / n_sampled if n_sampled > 0 else 0.0

    if not embeddings:
        return ClipResult(str(video_path), n_sampled, 0, None, detection_rate, None)

    # Intra-clip consistency: mean pairwise cosine similarity
    intra_sim: float | None = None
    if len(embeddings) >= 2:
        sims = [
            float(np.dot(embeddings[i], embeddings[j]))
            for i in range(len(embeddings))
            for j in range(i + 1, len(embeddings))
        ]
        intra_sim = float(np.mean(sims))

    mean_emb = np.mean(embeddings, axis=0)
    norm = float(np.linalg.norm(mean_emb))
    mean_emb = mean_emb / norm if norm > 0 else mean_emb

    return ClipResult(
        path=str(video_path),
        n_frames_sampled=n_sampled,
        n_faces_detected=len(embeddings),
        mean_embedding=mean_emb,
        detection_rate=detection_rate,
        intra_sim=intra_sim,
    )


# ---------------------------------------------------------------------------
# Metrics (pure numpy, no sklearn)
# ---------------------------------------------------------------------------

def _auc(labels: list[int], scores: list[float]) -> float:
    """Area Under the ROC Curve via trapezoid rule."""
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    pairs = sorted(zip(scores, labels), key=lambda x: -x[0])
    tp = fp = 0
    prev_fpr = prev_tpr = 0.0
    area = 0.0
    for _, label in pairs:
        if label == 1:
            tp += 1
        else:
            fp += 1
        tpr = tp / n_pos
        fpr = fp / n_neg
        area += (fpr - prev_fpr) * (tpr + prev_tpr) / 2
        prev_fpr, prev_tpr = fpr, tpr
    return area


def _eer(labels: list[int], scores: list[float]) -> float:
    """Approximate Equal Error Rate (where FPR ~ FNR)."""
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    pairs = sorted(zip(scores, labels), key=lambda x: -x[0])
    tp = fp = 0
    best_eer = 0.5
    best_diff = 1.0
    for _, label in pairs:
        if label == 1:
            tp += 1
        else:
            fp += 1
        fpr = fp / n_neg
        fnr = 1.0 - (tp / n_pos)
        diff = abs(fpr - fnr)
        if diff < best_diff:
            best_diff = diff
            best_eer = (fpr + fnr) / 2
    return best_eer


def _tar_at_far(labels: list[int], scores: list[float], target_far: float = 0.1) -> float:
    """True Acceptance Rate at the given False Acceptance Rate."""
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.0
    pairs = sorted(zip(scores, labels), key=lambda x: -x[0])
    tp = fp = 0
    for _, label in pairs:
        if label == 1:
            tp += 1
        else:
            fp += 1
        fpr = fp / n_neg
        if fpr >= target_far:
            return tp / n_pos
    return tp / n_pos


# ---------------------------------------------------------------------------
# Smoke mode
# ---------------------------------------------------------------------------

def run_smoke(
    video_path: str,
    detector_path: str = "models/scrfd_2.5g.onnx",
    embedder_path: str = "models/adaface_ir50.onnx",
    max_frames: int = 300,
    sample_step: int = 3,
    verbose: bool = True,
) -> VideoEvalResult:
    """Run the detection+embedding pipeline on one video; report throughput."""
    import os
    os.environ.setdefault("VMS_DB_URL", "postgresql://vms:vms@localhost:5434/vms_test")
    os.environ.setdefault("VMS_JWT_SECRET", "eval-only")
    os.environ.setdefault("VMS_REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("VMS_SCRFD_MODEL", detector_path)
    os.environ.setdefault("VMS_ADAFACE_MODEL", embedder_path)

    from vms.inference.detector import SCRFDDetector
    from vms.inference.embedder import AdaFaceEmbedder

    detector = SCRFDDetector.from_path(detector_path)
    embedder = AdaFaceEmbedder.from_path(embedder_path)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    fps_src = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if verbose:
        print(f"\n{'='*60}")
        print("  VMS Video Smoke Test")
        print(f"{'='*60}")
        print(f"  Video    : {video_path}")
        print(f"  Source   : {total_frames} frames at {fps_src:.1f} fps")
        print(f"  Sampling : every {sample_step} frames, up to {max_frames}")
        print(f"  Detector : {detector_path}")
        print(f"  Embedder : {embedder_path}")
        print(f"{'='*60}\n")

    result = VideoEvalResult(mode="smoke")
    intra_sims: list[float] = []
    t0 = time.time()

    frame_idx = 0
    while result.n_frames_processed < max_frames:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1
        if frame_idx % sample_step != 0:
            continue

        result.n_frames_processed += 1
        emb = _embed_frame(frame, detector, embedder)
        if emb is not None:
            result.n_faces_detected += 1

    cap.release()

    elapsed = time.time() - t0
    result.finalise_smoke(elapsed)

    if verbose:
        _print_smoke_summary(result)

    return result


# ---------------------------------------------------------------------------
# Verification mode (VoxCeleb1-style pairs)
# ---------------------------------------------------------------------------

def run_verification(
    pairs_file: str = "data/voxceleb_mini/pairs.csv",
    clips_dir: str = "data/voxceleb_mini/clips",
    detector_path: str = "models/scrfd_2.5g.onnx",
    embedder_path: str = "models/adaface_ir50.onnx",
    max_frames_per_clip: int = 30,
    verbose: bool = True,
) -> VideoEvalResult:
    """Face verification eval on VoxCeleb1-format pairs CSV.

    pairs.csv must have columns: label,clip1_path,clip2_path
    label = 1 (same person) or 0 (different person)
    paths are relative to clips_dir, or absolute.
    """
    import os
    os.environ.setdefault("VMS_DB_URL", "postgresql://vms:vms@localhost:5434/vms_test")
    os.environ.setdefault("VMS_JWT_SECRET", "eval-only")
    os.environ.setdefault("VMS_REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("VMS_SCRFD_MODEL", detector_path)
    os.environ.setdefault("VMS_ADAFACE_MODEL", embedder_path)

    from vms.inference.detector import SCRFDDetector
    from vms.inference.embedder import AdaFaceEmbedder

    pairs_path = Path(pairs_file)
    if not pairs_path.exists():
        raise FileNotFoundError(
            f"Pairs file not found: {pairs_file}\n"
            f"Run: python scripts/download_voxceleb_mini.py"
        )

    clips_base = Path(clips_dir)
    rows: list[tuple[int, Path, Path]] = []
    with pairs_path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            label = int(row["label"])
            p1 = Path(row["clip1_path"])
            p2 = Path(row["clip2_path"])
            if not p1.is_absolute():
                p1 = clips_base / p1
            if not p2.is_absolute():
                p2 = clips_base / p2
            rows.append((label, p1, p2))

    if verbose:
        print(f"\n{'='*60}")
        print("  VMS Video Face Verification (VoxCeleb1)")
        print(f"{'='*60}")
        print(f"  Pairs    : {len(rows)} ({sum(r[0] for r in rows)} same, {sum(1-r[0] for r in rows)} diff)")
        print(f"  Clips    : {clips_dir}")
        print(f"  Detector : {detector_path}")
        print(f"  Embedder : {embedder_path}")
        print(f"{'='*60}\n")

    detector = SCRFDDetector.from_path(detector_path)
    embedder = AdaFaceEmbedder.from_path(embedder_path)

    # Cache embeddings - each clip may appear in multiple pairs
    clip_cache: dict[str, ClipResult] = {}

    def get_clip(path: Path) -> ClipResult:
        key = str(path)
        if key not in clip_cache:
            clip_cache[key] = _embed_clip(path, detector, embedder, max_frames_per_clip)
        return clip_cache[key]

    result = VideoEvalResult(mode="verification", n_pairs_total=len(rows))

    for i, (label, p1, p2) in enumerate(rows):
        if verbose and (i + 1) % 10 == 0:
            print(f"  Processing pair {i+1}/{len(rows)}...")

        c1 = get_clip(p1)
        c2 = get_clip(p2)

        sim: float | None = None
        if c1.mean_embedding is not None and c2.mean_embedding is not None:
            sim = float(np.dot(c1.mean_embedding, c2.mean_embedding))

        result.pairs.append(PairResult(
            label=label,
            clip1_path=str(p1),
            clip2_path=str(p2),
            similarity=sim,
            clip1_det_rate=c1.detection_rate,
            clip2_det_rate=c2.detection_rate,
        ))

    result.finalise_verification()

    if verbose:
        _print_verification_summary(result)

    return result


# ---------------------------------------------------------------------------
# Reporters
# ---------------------------------------------------------------------------

def _print_smoke_summary(r: VideoEvalResult) -> None:
    print(f"\n{'='*60}")
    print("  SMOKE TEST SUMMARY")
    print(f"{'='*60}")
    print(f"  Frames processed : {r.n_frames_processed}")
    print(f"  Faces detected   : {r.n_faces_detected} ({r.detection_rate:.1%})")
    print(f"  Processing speed : {r.fps:.1f} fps  (sampled frames)")
    print()
    if r.passed:
        print("  VERDICT: PASS - video pipeline is functional")
    else:
        print("  VERDICT: FAIL")
        for reason in r.fail_reasons:
            print(f"    * {reason}")
    print(f"{'='*60}\n")


def _print_verification_summary(r: VideoEvalResult) -> None:
    print(f"\n{'='*60}")
    print("  FACE VERIFICATION SUMMARY  (VoxCeleb1)")
    print(f"{'='*60}")
    print(f"  Pairs total      : {r.n_pairs_total}")
    print(f"  Pairs usable     : {r.n_pairs_usable} ({r.usable_pair_rate:.1%})"
          f"  {'OK' if r.usable_pair_rate >= USABLE_PAIRS_MIN else 'FAIL'}")
    print()
    print(f"  AUC              : {r.auc:.4f}"
          f"  {'OK' if r.auc >= AUC_MIN else 'FAIL'} (need >= {AUC_MIN})")
    print(f"  EER              : {r.eer:.4f}"
          f"  {'OK' if r.eer <= EER_MAX else 'FAIL'} (need <= {EER_MAX})")
    print(f"  TAR@FAR=0.1      : {r.tar_at_far01:.4f}")
    print()
    if r.passed:
        print("  VERDICT: PASS - face recognition is accurate on video")
    else:
        print("  VERDICT: FAIL")
        for reason in r.fail_reasons:
            print(f"    * {reason}")

    no_face = [p for p in r.pairs if p.similarity is None]
    if no_face and len(no_face) <= 10:
        print(f"\n  Clips with no detected face ({len(no_face)}):")
        seen: set[str] = set()
        for p in no_face:
            for path in (p.clip1_path, p.clip2_path):
                if path not in seen and (
                    ClipResult.__new__(ClipResult) or True
                ):
                    # just print unique paths that failed
                    seen.add(path)
                    if p.clip1_det_rate == 0.0 and path == p.clip1_path:
                        print(f"    {Path(path).name}  (clip1, det_rate=0)")
                    if p.clip2_det_rate == 0.0 and path == p.clip2_path:
                        print(f"    {Path(path).name}  (clip2, det_rate=0)")

    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", help="Single video for smoke test")
    src.add_argument("--pairs", help="CSV of verification pairs (VoxCeleb1 format)")
    p.add_argument("--clips-dir", default="data/voxceleb_mini/clips",
                   help="Base directory for clip paths (verification mode only)")
    p.add_argument("--detector", default="models/scrfd_2.5g.onnx")
    p.add_argument("--embedder", default="models/adaface_ir50.onnx")
    p.add_argument("--max-frames", type=int, default=0,
                   help="Max frames to sample per clip (0 = use default per mode)")
    p.add_argument("--quiet", action="store_true", help="Suppress verbose output")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    verbose = not args.quiet

    if args.video:
        max_f = args.max_frames or 300
        result = run_smoke(
            args.video, args.detector, args.embedder,
            max_frames=max_f, verbose=verbose,
        )
    else:
        max_f = args.max_frames or 30
        result = run_verification(
            args.pairs, args.clips_dir, args.detector, args.embedder,
            max_frames_per_clip=max_f, verbose=verbose,
        )

    sys.exit(0 if result.passed else 1)
