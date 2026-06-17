"""Face pipeline accuracy evaluation.

Enrols one image per person (01.jpg) into a FAISS-style gallery, then probes
all remaining images (02.jpg-06.jpg) and measures Rank-1 accuracy, genuine-pair
similarity distribution, and impostor-pair similarity distribution.

Usage
-----
    python scripts/eval_face_accuracy.py
    python scripts/eval_face_accuracy.py --dataset employees/ --detector models/scrfd_2.5g.onnx
    python scripts/eval_face_accuracy.py --help

Returns exit code 0 when all pass thresholds are met, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pass/fail thresholds (conservative - real-world employee photos)
# ---------------------------------------------------------------------------
RANK1_MIN = 0.90          # at least 90% of detected-face probes match correctly
MAX_IMPOSTOR_SIM = 0.72   # no impostor pair must reach the live threshold
MIN_GENUINE_SIM = 0.62    # genuine pairs (same person) must clear the soft-match floor
DETECTION_RATE_MIN = 0.80 # at least 80% of probe images must yield a detectable face


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ProbeResult:
    true_person: str
    image_name: str
    predicted_person: str | None   # None = face not detected
    top_sim: float | None
    genuine_sim: float | None      # similarity against the correct gallery entry
    correct: bool
    status: str                    # "ok" | "no_face" | "enrol_failed"


@dataclass
class EvalResult:
    dataset_dir: str
    n_persons: int
    n_enrolled: int
    n_probes_total: int
    probes: list[ProbeResult] = field(default_factory=list)

    # computed by finalise()
    n_detected: int = 0
    n_correct: int = 0
    rank1_accuracy: float = 0.0
    detection_rate: float = 0.0
    genuine_sims: list[float] = field(default_factory=list)
    impostor_sims: list[float] = field(default_factory=list)
    mean_genuine: float = 0.0
    min_genuine: float = 0.0
    max_impostor: float = 0.0

    passed: bool = False
    fail_reasons: list[str] = field(default_factory=list)

    def finalise(self) -> None:
        detected = [p for p in self.probes if p.status == "ok"]
        self.n_detected = len(detected)
        self.n_correct = sum(1 for p in detected if p.correct)
        self.detection_rate = self.n_detected / self.n_probes_total if self.n_probes_total else 0.0
        self.rank1_accuracy = self.n_correct / self.n_detected if self.n_detected else 0.0
        self.genuine_sims = [p.genuine_sim for p in detected if p.genuine_sim is not None]  # type: ignore[misc]
        self.mean_genuine = float(np.mean(self.genuine_sims)) if self.genuine_sims else 0.0
        self.min_genuine = float(np.min(self.genuine_sims)) if self.genuine_sims else 0.0
        self.max_impostor = max(self.impostor_sims) if self.impostor_sims else 0.0

        self.fail_reasons = []
        if self.rank1_accuracy < RANK1_MIN:
            self.fail_reasons.append(
                f"Rank-1 {self.rank1_accuracy:.1%} < {RANK1_MIN:.0%} required"
            )
        if self.max_impostor >= MAX_IMPOSTOR_SIM:
            self.fail_reasons.append(
                f"Impostor pair reached {self.max_impostor:.4f} >= threshold {MAX_IMPOSTOR_SIM}"
            )
        if self.genuine_sims and self.min_genuine < MIN_GENUINE_SIM:
            self.fail_reasons.append(
                f"Genuine pair dipped to {self.min_genuine:.4f} < soft floor {MIN_GENUINE_SIM}"
            )
        if self.detection_rate < DETECTION_RATE_MIN:
            self.fail_reasons.append(
                f"Detection rate {self.detection_rate:.1%} < {DETECTION_RATE_MIN:.0%} required"
            )
        self.passed = len(self.fail_reasons) == 0


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------

def _load_bgr(path: Path) -> np.ndarray[Any, np.dtype[Any]] | None:
    img = cv2.imread(str(path))
    if img is None:
        logger.warning("Could not load image: %s", path)
    return img


def _embed_image(
    path: Path,
    detector: Any,
    embedder: Any,
    min_face_px: int = 20,
) -> np.ndarray[Any, np.dtype[Any]] | None:
    """Detect the largest face in an image and return its L2-normalised embedding."""
    frame = _load_bgr(path)
    if frame is None:
        return None

    faces = detector.detect(frame)
    if not faces:
        return None

    # Pick the largest face (most likely to be the subject of a portrait photo)
    best = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

    # Re-check minimum size with the eval-specific threshold (photos may be smaller than live stream)
    x1, y1, x2, y2 = best.bbox
    if (x2 - x1) < min_face_px or (y2 - y1) < min_face_px:
        return None

    result = embedder.embed(best, frame)
    if result is None or not result.embedding:
        return None

    emb = np.array(result.embedding, dtype=np.float32)
    norm = np.linalg.norm(emb)
    return emb / norm if norm > 0 else emb


# ---------------------------------------------------------------------------
# Main eval function (importable)
# ---------------------------------------------------------------------------

def run_eval(
    dataset_dir: str = "employees",
    detector_path: str = "models/scrfd_2.5g.onnx",
    embedder_path: str = "models/adaface_ir50.onnx",
    gallery_filename: str = "01.jpg",
    verbose: bool = True,
) -> EvalResult:
    """Run face accuracy evaluation and return an EvalResult.

    dataset_dir must contain one subdirectory per person, each with at least
    two JPEG images: gallery_filename (enrolled) and one or more probe images.
    """
    import os
    os.environ.setdefault("VMS_DB_URL", "postgresql://vms:vms@localhost:5434/vms_test")
    os.environ.setdefault("VMS_JWT_SECRET", "eval-only")
    os.environ.setdefault("VMS_REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("VMS_SCRFD_MODEL", detector_path)
    os.environ.setdefault("VMS_ADAFACE_MODEL", embedder_path)
    os.environ.setdefault("VMS_BYTETRACK_CONFIG", "bytetrack_custom.yaml")

    from vms.inference.detector import SCRFDDetector
    from vms.inference.embedder import AdaFaceEmbedder

    dataset = Path(dataset_dir)
    if not dataset.is_dir():
        raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")

    person_dirs = sorted(
        [d for d in dataset.iterdir() if d.is_dir()],
        key=lambda d: d.name.lower(),
    )
    if not person_dirs:
        raise ValueError(f"No person subdirectories found in {dataset_dir}")

    if verbose:
        print(f"\n{'='*60}")
        print("  VMS Face Pipeline - Accuracy Evaluation")
        print(f"{'='*60}")
        print(f"  Dataset  : {dataset.resolve()}")
        print(f"  Detector : {detector_path}")
        print(f"  Embedder : {embedder_path}")
        print(f"  Persons  : {len(person_dirs)}")
        print(f"{'='*60}\n")

    detector = SCRFDDetector.from_path(detector_path)
    embedder = AdaFaceEmbedder.from_path(embedder_path)

    # ------------------------------------------------------------------
    # Step 1: Enrolment - one gallery embedding per person
    # ------------------------------------------------------------------
    gallery: dict[str, np.ndarray[Any, np.dtype[Any]]] = {}
    enrol_failed: list[str] = []

    if verbose:
        print("[ ENROLMENT ]")

    for pdir in person_dirs:
        gallery_img = pdir / gallery_filename
        if not gallery_img.exists():
            enrol_failed.append(pdir.name)
            if verbose:
                print(f"  FAIL {pdir.name:20s}  - {gallery_filename} not found")
            continue
        emb = _embed_image(gallery_img, detector, embedder)
        if emb is None:
            enrol_failed.append(pdir.name)
            if verbose:
                print(f"  FAIL {pdir.name:20s}  - no face detected in {gallery_filename}")
        else:
            gallery[pdir.name] = emb
            if verbose:
                print(f"  OK   {pdir.name:20s}  - enrolled")

    if verbose:
        print(f"\n  Enrolled {len(gallery)}/{len(person_dirs)} persons\n")

    # ------------------------------------------------------------------
    # Step 2: Probing
    # ------------------------------------------------------------------
    probe_images: list[tuple[str, Path]] = []
    for pdir in person_dirs:
        for img_path in sorted(pdir.glob("*.jpg")):
            if img_path.name != gallery_filename:
                probe_images.append((pdir.name, img_path))

    result = EvalResult(
        dataset_dir=str(dataset.resolve()),
        n_persons=len(person_dirs),
        n_enrolled=len(gallery),
        n_probes_total=len(probe_images),
    )

    if verbose:
        print("[ PROBING ]")
        print(f"  {'Person':<20s}  {'Image':<10s}  {'Predicted':<20s}  {'Sim':>6s}  {'Genuine':>7s}  Result")
        print(f"  {'-'*20}  {'-'*10}  {'-'*20}  {'-'*6}  {'-'*7}  ------")

    for true_person, img_path in probe_images:
        emb = _embed_image(img_path, detector, embedder)

        if emb is None:
            result.probes.append(ProbeResult(
                true_person=true_person,
                image_name=img_path.name,
                predicted_person=None,
                top_sim=None,
                genuine_sim=None,
                correct=False,
                status="no_face",
            ))
            if verbose:
                print(f"  {true_person:<20s}  {img_path.name:<10s}  {'-':<20s}  {'-':>6s}  {'-':>7s}  NO FACE")
            continue

        # Similarities against every gallery entry
        sims = {
            name: float(np.dot(emb, gallery_emb))
            for name, gallery_emb in gallery.items()
        }
        # Collect all impostor sims (different person)
        result.impostor_sims.extend(
            sim for name, sim in sims.items() if name != true_person
        )

        if not sims:
            result.probes.append(ProbeResult(
                true_person=true_person,
                image_name=img_path.name,
                predicted_person=None,
                top_sim=None,
                genuine_sim=None,
                correct=False,
                status="no_face",
            ))
            continue

        top_match = max(sims, key=sims.__getitem__)
        top_sim = sims[top_match]
        genuine_sim = sims.get(true_person)
        correct = top_match == true_person

        result.probes.append(ProbeResult(
            true_person=true_person,
            image_name=img_path.name,
            predicted_person=top_match,
            top_sim=top_sim,
            genuine_sim=genuine_sim,
            correct=correct,
            status="ok",
        ))

        if verbose:
            tick = "OK  " if correct else "FAIL"
            gen_str = f"{genuine_sim:.4f}" if genuine_sim is not None else "-"
            print(
                f"  {true_person:<20s}  {img_path.name:<10s}  {top_match:<20s}"
                f"  {top_sim:>6.4f}  {gen_str:>7s}  {tick}"
            )

    # ------------------------------------------------------------------
    # Step 3: Compute summary statistics + pass/fail
    # ------------------------------------------------------------------
    result.finalise()

    if verbose:
        _print_summary(result)

    return result


def _print_summary(r: EvalResult) -> None:
    print(f"\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    print(f"  Persons enrolled    : {r.n_enrolled}/{r.n_persons}")
    print(f"  Probes total        : {r.n_probes_total}")
    print(f"  Faces detected      : {r.n_detected}/{r.n_probes_total}"
          f"  ({r.detection_rate:.1%})"
          f"  {'OK' if r.detection_rate >= DETECTION_RATE_MIN else 'FAIL'}")
    print()
    print(f"  Genuine pairs       : {len(r.genuine_sims)}")
    if r.genuine_sims:
        print(f"    mean similarity   : {r.mean_genuine:.4f}")
        print(f"    min  similarity   : {r.min_genuine:.4f}"
              f"  {'OK' if r.min_genuine >= MIN_GENUINE_SIM else 'FAIL BELOW SOFT FLOOR'}")
    print()
    print(f"  Impostor pairs      : {len(r.impostor_sims)}")
    if r.impostor_sims:
        print(f"    max  similarity   : {r.max_impostor:.4f}"
              f"  {'OK' if r.max_impostor < MAX_IMPOSTOR_SIM else 'FAIL EXCEEDS THRESHOLD'}")
    print()
    print(f"  Rank-1 accuracy     : {r.n_correct}/{r.n_detected}"
          f"  ({r.rank1_accuracy:.1%})"
          f"  {'OK' if r.rank1_accuracy >= RANK1_MIN else 'FAIL'}")
    print()
    if r.passed:
        print("  VERDICT: PASS - pipeline is working correctly")
    else:
        print("  VERDICT: FAIL")
        for reason in r.fail_reasons:
            print(f"    * {reason}")

    # Highlight wrong predictions
    wrong = [p for p in r.probes if p.status == "ok" and not p.correct]
    if wrong:
        print(f"\n  Wrong predictions ({len(wrong)}):")
        for p in wrong:
            top_str = f"{p.top_sim:.4f}" if p.top_sim is not None else "n/a"
            gen_str = f"{p.genuine_sim:.4f}" if p.genuine_sim is not None else "n/a"
            print(f"    {p.true_person}/{p.image_name}"
                  f" -> predicted '{p.predicted_person}'"
                  f" (sim={top_str}, genuine={gen_str})")

    missed = [p for p in r.probes if p.status == "no_face"]
    if missed:
        print(f"\n  No face detected ({len(missed)}):")
        for p in missed:
            print(f"    {p.true_person}/{p.image_name}")

    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", default="employees", help="Path to dataset directory")
    p.add_argument("--detector", default="models/scrfd_2.5g.onnx", help="SCRFD ONNX path")
    p.add_argument("--embedder", default="models/adaface_ir50.onnx", help="AdaFace ONNX path")
    p.add_argument("--gallery-img", default="01.jpg", help="Filename to use as gallery enrolment")
    p.add_argument("--json", dest="json_out", metavar="FILE", help="Write JSON results to file")
    p.add_argument("--quiet", action="store_true", help="Suppress per-image output")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = run_eval(
        dataset_dir=args.dataset,
        detector_path=args.detector,
        embedder_path=args.embedder,
        gallery_filename=args.gallery_img,
        verbose=not args.quiet,
    )
    if args.json_out:
        output = {
            "dataset_dir": result.dataset_dir,
            "n_persons": result.n_persons,
            "n_enrolled": result.n_enrolled,
            "n_probes_total": result.n_probes_total,
            "n_detected": result.n_detected,
            "n_correct": result.n_correct,
            "rank1_accuracy": result.rank1_accuracy,
            "detection_rate": result.detection_rate,
            "mean_genuine_sim": result.mean_genuine,
            "min_genuine_sim": result.min_genuine,
            "max_impostor_sim": result.max_impostor,
            "passed": result.passed,
            "fail_reasons": result.fail_reasons,
        }
        Path(args.json_out).write_text(json.dumps(output, indent=2))
        print(f"JSON results written to {args.json_out}")
    sys.exit(0 if result.passed else 1)
