"""OSNet AIN body Re-ID simulation on DukeMTMC-reID.

Runs the standard Re-ID evaluation protocol:
  Query set  : query/           (2,228 images, 8 cameras)
  Gallery set: bounding_box_test/ (17,661 images)

Metrics computed:
  Rank-1 / Rank-5 / Rank-10 accuracy (CMC curve)
  mAP  (mean Average Precision)
  Cosine similarity distribution — same-person vs different-person cross-camera
  Production threshold recommendations for reid_body_confirmed_sim /
  reid_body_cross_cam_sim based on observed similarity ranges

Usage:
    python scripts/simulate_osnet_reid.py
    python scripts/simulate_osnet_reid.py --device cuda  # GPU
    python scripts/simulate_osnet_reid.py --max-query 200 --device cpu  # quick test
    python scripts/simulate_osnet_reid.py --save-embeddings  # cache for re-runs

Requires: torchreid, torch, numpy, opencv-python
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("simulate_osnet")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("VMS_DB_URL", "postgresql://localhost/vms_simulate_dummy")
os.environ.setdefault("VMS_JWT_SECRET", "simulate-script-not-a-real-secret")

# ---------------------------------------------------------------------------
# DukeMTMC filename parser
# ---------------------------------------------------------------------------

_DUKE_RE = re.compile(r"^(\d{4})_c(\d)_f(\d+)\.jpg$", re.IGNORECASE)


@dataclass(frozen=True)
class _ImgMeta:
    path: Path
    person_id: int
    camera_id: int
    frame_idx: int


def parse_folder(folder: Path) -> list[_ImgMeta]:
    out: list[_ImgMeta] = []
    for p in sorted(folder.glob("*.jpg")):
        m = _DUKE_RE.match(p.name)
        if not m:
            continue
        pid, cid, fidx = int(m[1]), int(m[2]), int(m[3])
        if pid <= 0:
            continue  # skip distractor class (pid=0000 or negative)
        out.append(_ImgMeta(path=p, person_id=pid, camera_id=cid, frame_idx=fidx))
    return out


# ---------------------------------------------------------------------------
# Embedding computation (batched)
# ---------------------------------------------------------------------------

def build_extractor(model_path: str, device: str) -> Any:
    """Load torchreid FeatureExtractor for OSNet AIN x1.0 msmt17."""
    try:
        from torchreid.utils import FeatureExtractor  # type: ignore[import-not-found]
    except ImportError:
        print("ERROR: torchreid not installed.")
        print("  Install: pip install torchreid  (or from deep-person-reid)")
        sys.exit(1)

    if not Path(model_path).exists():
        print(f"ERROR: model not found at {model_path}")
        print("  Run: python scripts/download_osnet_ain_msmt17.py")
        sys.exit(1)

    print(f"Loading OSNet AIN x1.0 msmt17 from {model_path} (device={device}) ...")
    extractor = FeatureExtractor(
        model_name="osnet_ain_x1_0",
        model_path=model_path,
        device=device,
        verbose=False,
    )
    print("  Model ready.")
    return extractor


def embed_batch(
    extractor: Any,
    imgs: list[_ImgMeta],
    batch_size: int = 64,
    desc: str = "",
) -> np.ndarray:  # type: ignore[type-arg]
    """Return (N, 512) float32 L2-normalised embeddings for a list of images."""
    import torch

    all_vecs: list[np.ndarray] = []  # type: ignore[type-arg]
    n = len(imgs)
    t0 = time.time()

    for start in range(0, n, batch_size):
        batch = imgs[start : start + batch_size]
        crops: list[np.ndarray] = []  # type: ignore[type-arg]
        for img in batch:
            bgr = cv2.imread(str(img.path))
            if bgr is None:
                # fallback: black image at correct size
                bgr = np.zeros((128, 64, 3), dtype=np.uint8)
            crops.append(bgr)

        with torch.no_grad():
            feats = extractor(crops)  # (B, 512) raw feature tensor from torchreid backbone
        feats_np = feats.cpu().numpy().astype(np.float32)
        # L2-normalise so inner product == cosine similarity in [-1, 1]
        norms = np.linalg.norm(feats_np, axis=1, keepdims=True) + 1e-8
        all_vecs.append(feats_np / norms)

        done = min(start + batch_size, n)
        elapsed = time.time() - t0
        eta = elapsed / done * (n - done) if done > 0 else 0
        print(
            f"\r  {desc}: {done}/{n}  ({done/max(elapsed,1e-6):.0f} img/s  "
            f"ETA {eta:.0f}s)    ",
            end="",
            flush=True,
        )

    print()
    return np.concatenate(all_vecs, axis=0)  # (N, 512)


# ---------------------------------------------------------------------------
# Standard Re-ID evaluation (CMC + mAP)
# ---------------------------------------------------------------------------

def evaluate(
    query_imgs: list[_ImgMeta],
    gallery_imgs: list[_ImgMeta],
    query_embs: np.ndarray,   # (Nq, 512)
    gallery_embs: np.ndarray, # (Ng, 512)
    top_k: tuple[int, ...] = (1, 5, 10),
) -> dict[str, float]:
    """Compute CMC@k and mAP following standard Re-ID evaluation protocol.

    Exclusion rule: for query (person P, cam C), gallery entries with the
    SAME person P AND SAME camera C are excluded (same-camera junk).
    """
    # Cosine similarity matrix: (Nq, Ng)  —  both sets are already L2-normalised
    sim_matrix: np.ndarray = query_embs @ gallery_embs.T  # type: ignore[type-arg]

    cmc_hits = {k: 0 for k in top_k}
    ap_sum = 0.0
    n_valid = 0

    gallery_pids = np.array([g.person_id for g in gallery_imgs], dtype=np.int32)
    gallery_cids = np.array([g.camera_id for g in gallery_imgs], dtype=np.int32)

    for qi, qmeta in enumerate(query_imgs):
        sims = sim_matrix[qi]  # (Ng,)

        # Junk mask: same person + same camera → exclude from ranking
        junk = (gallery_pids == qmeta.person_id) & (gallery_cids == qmeta.camera_id)
        # True positive mask: same person, different camera
        pos = (gallery_pids == qmeta.person_id) & (gallery_cids != qmeta.camera_id)

        if pos.sum() == 0:
            # No valid positives → skip this query
            continue
        n_valid += 1

        # Sort by descending similarity, excluding junk
        order = np.argsort(-sims)
        keep = ~junk[order]
        ranked_pos = pos[order][keep]   # boolean array: is rank-r a true positive?

        # CMC
        cum = np.cumsum(ranked_pos)
        for k in top_k:
            if cum[min(k, len(cum)) - 1] >= 1:
                cmc_hits[k] += 1

        # AP
        n_pos = int(pos.sum())
        hit_at_r = np.cumsum(ranked_pos).astype(float)
        r = np.arange(1, len(ranked_pos) + 1, dtype=float)
        precision_at_r = hit_at_r / r
        # Only count ranks where a positive appears
        ap = float(np.sum(precision_at_r * ranked_pos)) / n_pos
        ap_sum += ap

    results: dict[str, float] = {}
    for k in top_k:
        results[f"rank{k}"] = cmc_hits[k] / max(n_valid, 1) * 100.0
    results["mAP"] = ap_sum / max(n_valid, 1) * 100.0
    results["n_valid_queries"] = float(n_valid)
    return results


# ---------------------------------------------------------------------------
# Threshold analysis
# ---------------------------------------------------------------------------

def threshold_analysis(
    query_imgs: list[_ImgMeta],
    gallery_imgs: list[_ImgMeta],
    query_embs: np.ndarray,
    gallery_embs: np.ndarray,
    sample_pairs: int = 50_000,
) -> dict[str, Any]:
    """Compute cosine similarity distributions for same-person vs different-person pairs.

    Returns statistics to guide production threshold tuning.
    """
    rng = np.random.default_rng(42)
    gallery_pids = np.array([g.person_id for g in gallery_imgs], dtype=np.int32)
    gallery_cids = np.array([g.camera_id for g in gallery_imgs], dtype=np.int32)

    same_sims: list[float] = []
    diff_sims: list[float] = []

    # Sample same-person cross-camera pairs from query vs gallery
    for qi in rng.choice(len(query_imgs), size=min(500, len(query_imgs)), replace=False):
        qmeta = query_imgs[qi]
        sims = query_embs[qi] @ gallery_embs.T

        # Same person, different camera
        pos_idx = np.where(
            (gallery_pids == qmeta.person_id) & (gallery_cids != qmeta.camera_id)
        )[0]
        if len(pos_idx) > 0:
            for idx in pos_idx[:10]:
                same_sims.append(float(sims[idx]))

        # Different person (random sample)
        neg_idx = np.where(gallery_pids != qmeta.person_id)[0]
        for idx in rng.choice(neg_idx, size=min(20, len(neg_idx)), replace=False):
            diff_sims.append(float(sims[idx]))

    s = np.array(same_sims, dtype=np.float32)
    d = np.array(diff_sims, dtype=np.float32)

    def pct(arr: np.ndarray, q: float) -> float:
        return float(np.percentile(arr, q))

    # Find threshold where 95% of same-person pairs are above (conservative)
    threshold_conservative = pct(s, 5)   # 5th pct of same-person → 95% recall
    # Find threshold where 99% of same-person pairs are above (very conservative)
    threshold_loose = pct(s, 1)          # 1st pct

    # Find where false positive rate = 1% (1% of different-person pairs above)
    threshold_fp1 = pct(d, 99)           # 99th pct of diff-person

    # Recommended: balance between recall and precision
    # Use the higher of (fp1%) and (5th pct of same) with a margin
    recommended = max(threshold_conservative, threshold_fp1) - 0.02

    return {
        "same_person": {
            "n": len(s),
            "min": float(s.min()),
            "p1": pct(s, 1),
            "p5": pct(s, 5),
            "p25": pct(s, 25),
            "median": pct(s, 50),
            "p75": pct(s, 75),
            "p95": pct(s, 95),
            "max": float(s.max()),
        },
        "diff_person": {
            "n": len(d),
            "min": float(d.min()),
            "median": pct(d, 50),
            "p95": pct(d, 95),
            "p99": pct(d, 99),
            "max": float(d.max()),
        },
        "threshold_conservative": threshold_conservative,
        "threshold_loose": threshold_loose,
        "threshold_fp1pct": threshold_fp1,
        "recommended": recommended,
    }


# ---------------------------------------------------------------------------
# Camera-pair accuracy breakdown
# ---------------------------------------------------------------------------

def camera_pair_accuracy(
    query_imgs: list[_ImgMeta],
    gallery_imgs: list[_ImgMeta],
    query_embs: np.ndarray,
    gallery_embs: np.ndarray,
) -> dict[str, float]:
    """Rank-1 accuracy broken down by query camera → gallery camera pair."""
    gallery_pids = np.array([g.person_id for g in gallery_imgs], dtype=np.int32)
    gallery_cids = np.array([g.camera_id for g in gallery_imgs], dtype=np.int32)

    hits: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)

    sim_matrix = query_embs @ gallery_embs.T

    for qi, qmeta in enumerate(query_imgs):
        sims = sim_matrix[qi]
        junk = (gallery_pids == qmeta.person_id) & (gallery_cids == qmeta.camera_id)
        pos = (gallery_pids == qmeta.person_id) & (gallery_cids != qmeta.camera_id)
        if pos.sum() == 0:
            continue

        order = np.argsort(-sims)
        keep = ~junk[order]
        ranked_pos = pos[order][keep]

        # For camera-pair breakdown, attribute to the query's camera
        cam_key = f"c{qmeta.camera_id}"
        total[cam_key] += 1
        if len(ranked_pos) > 0 and ranked_pos[0]:
            hits[cam_key] += 1

    return {k: hits[k] / total[k] * 100.0 for k in total}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(
    metrics: dict[str, float],
    thresh: dict[str, Any],
    cam_accuracy: dict[str, float],
    dataset_path: str,
    args: argparse.Namespace,
) -> None:
    w = "=" * 62
    print(f"\n{w}")
    print("  OSNet AIN x1.0 msmt17 — DukeMTMC-reID BENCHMARK")
    print(w)
    print(f"  Dataset : {dataset_path}")
    print(f"  Model   : {args.model}")
    print(f"  Device  : {args.device}")
    print(f"  Queries : {int(metrics['n_valid_queries'])}")
    print()

    print("  --- CMC Accuracy -------------------------------------------")
    print(f"  Rank-1  : {metrics['rank1']:6.2f}%")
    print(f"  Rank-5  : {metrics['rank5']:6.2f}%")
    print(f"  Rank-10 : {metrics['rank10']:6.2f}%")
    print(f"  mAP     : {metrics['mAP']:6.2f}%")
    print()

    print("  --- Cosine Similarity Distribution -----------------------")
    s = thresh["same_person"]
    d = thresh["diff_person"]
    print(f"  Same person (cross-cam)  n={s['n']}")
    print(f"    p1={s['p1']:.3f}  p5={s['p5']:.3f}  p25={s['p25']:.3f}"
          f"  median={s['median']:.3f}  p75={s['p75']:.3f}  p95={s['p95']:.3f}")
    print(f"  Different person         n={d['n']}")
    print(f"    median={d['median']:.3f}  p95={d['p95']:.3f}  p99={d['p99']:.3f}"
          f"  max={d['max']:.3f}")
    print()

    print("  --- Per-Camera Rank-1 ------------------------------------")
    for cam, acc in sorted(cam_accuracy.items()):
        bar_len = int(acc / 2)
        bar = "#" * bar_len + "." * (50 - bar_len)
        print(f"  {cam}: {acc:5.1f}%  |{bar}|")
    print()

    print("  --- Production Threshold Recommendations ----------------")
    print(f"  Separation gap  : {s['p5'] - d['p99']:.3f}")
    print(f"    (same-p5 {s['p5']:.3f} vs diff-p99 {d['p99']:.3f})")
    print()
    print(f"  Conservative (95% recall, ~1% FP):")
    print(f"    reid_body_confirmed_sim  = {thresh['threshold_conservative']:.2f}")
    print(f"    reid_body_cross_cam_sim  = {thresh['threshold_conservative'] + 0.05:.2f}")
    print()
    print(f"  Balanced (recommended starting point):")
    print(f"    reid_body_confirmed_sim  = {thresh['recommended']:.2f}")
    print(f"    reid_body_cross_cam_sim  = {thresh['recommended'] + 0.05:.2f}")
    print()
    print(f"  Loose (maximize recall, accept ~5% FP):")
    print(f"    reid_body_confirmed_sim  = {thresh['threshold_loose']:.2f}")
    print(f"    reid_body_cross_cam_sim  = {thresh['threshold_loose'] + 0.05:.2f}")
    print()
    print("  Current config values (vms/config.py):")
    print("    reid_body_confirmed_sim  = 0.58  (default)")
    print("    reid_body_cross_cam_sim  = 0.65  (default)")
    gap_conf = s["p5"] - 0.58
    gap_cross = s["p5"] - 0.65
    conf_ok = "OK — above p5" if gap_conf >= 0 else f"RISKY — below p5 by {-gap_conf:.3f}"
    cross_ok = "OK — above p5" if gap_cross >= 0 else f"RISKY — below p5 by {-gap_cross:.3f}"
    print(f"    confirmed_sim status : {conf_ok}")
    print(f"    cross_cam_sim status : {cross_ok}")
    print(w)
    print()
    print("  Next step: update config with recommended values, then")
    print("  wire BodyEmbedder into InferenceEngine production worker.")
    print(f"{w}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="OSNet DukeMTMC-reID simulation")
    parser.add_argument(
        "--dataset",
        default="",
        help="Path to DukeMTMC-reID root (auto-downloads via kagglehub if empty)",
    )
    parser.add_argument(
        "--model",
        default=str(REPO_ROOT / "models" / "osnet_ain_x1_0_msmt17.pth"),
        help="Path to OSNet AIN msmt17 .pth weights",
    )
    parser.add_argument(
        "--device", default="cpu", choices=["cpu", "cuda"],
        help="Inference device (default: cpu)"
    )
    parser.add_argument(
        "--max-query", type=int, default=0,
        help="Limit queries (0=all 2228). Use 200 for a quick test.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=64,
        help="Images per forward pass (default 64)",
    )
    parser.add_argument(
        "--save-embeddings", action="store_true",
        help="Cache embeddings to data/duke_embeddings/ for re-runs",
    )
    parser.add_argument(
        "--quick", action="store_true",
        help=(
            "Fast mode: only embed gallery images whose person_id appears in the "
            "selected queries plus a random sample of 300 distractors. "
            "Reduces gallery from 17K to ~2K. Use with --max-query 200 for a 3-min run."
        ),
    )
    args = parser.parse_args()

    # Resolve dataset path
    if args.dataset:
        duke_root = Path(args.dataset)
    else:
        print("Resolving DukeMTMC-reID via kagglehub ...")
        try:
            import kagglehub
            raw = kagglehub.dataset_download("igorkrashenyi/dukemtmc-reid")
        except Exception as exc:
            print(f"ERROR: kagglehub download failed: {exc}")
            sys.exit(1)
        raw_root = Path(raw)
        # The dataset extracts to a numbered version folder
        candidates = list(raw_root.rglob("bounding_box_test"))
        if not candidates:
            print(f"ERROR: bounding_box_test not found under {raw_root}")
            sys.exit(1)
        duke_root = candidates[0].parent

    query_dir = duke_root / "query"
    gallery_dir = duke_root / "bounding_box_test"
    if not query_dir.exists() or not gallery_dir.exists():
        print(f"ERROR: expected query/ and bounding_box_test/ under {duke_root}")
        sys.exit(1)

    print(f"Dataset root : {duke_root}")

    # Parse images
    print("Parsing image metadata ...")
    query_imgs = parse_folder(query_dir)
    gallery_imgs = parse_folder(gallery_dir)
    print(f"  Query  : {len(query_imgs)} images")
    print(f"  Gallery: {len(gallery_imgs)} images")

    if args.max_query > 0:
        query_imgs = query_imgs[: args.max_query]
        print(f"  Limited to {len(query_imgs)} queries (--max-query {args.max_query})")

    # --quick: trim gallery to query person_ids + random distractors
    if args.quick:
        rng_q = np.random.default_rng(0)
        query_pids = {q.person_id for q in query_imgs}
        relevant = [g for g in gallery_imgs if g.person_id in query_pids]
        distractors = [g for g in gallery_imgs if g.person_id not in query_pids]
        n_dist = min(300, len(distractors))
        distractor_sample = [
            distractors[i]
            for i in rng_q.choice(len(distractors), size=n_dist, replace=False)
        ]
        gallery_imgs = relevant + distractor_sample
        print(
            f"  --quick: gallery trimmed to {len(relevant)} relevant "
            f"+ {n_dist} distractor images = {len(gallery_imgs)} total"
        )

    # Load model
    extractor = build_extractor(args.model, args.device)

    # Check for cached embeddings
    cache_dir = REPO_ROOT / "data" / "duke_embeddings"
    q_cache = cache_dir / f"query_{len(query_imgs)}.npy"
    g_cache = cache_dir / f"gallery_{len(gallery_imgs)}.npy"

    if args.save_embeddings and q_cache.exists() and g_cache.exists():
        print("Loading cached embeddings ...")
        query_embs = np.load(str(q_cache))
        gallery_embs = np.load(str(g_cache))
    else:
        print(f"\nComputing query embeddings ({len(query_imgs)} images) ...")
        query_embs = embed_batch(extractor, query_imgs, args.batch_size, "Query ")

        print(f"Computing gallery embeddings ({len(gallery_imgs)} images) ...")
        gallery_embs = embed_batch(extractor, gallery_imgs, args.batch_size, "Gallery")

        if args.save_embeddings:
            cache_dir.mkdir(parents=True, exist_ok=True)
            np.save(str(q_cache), query_embs)
            np.save(str(g_cache), gallery_embs)
            print(f"  Embeddings cached to {cache_dir}")

    # Evaluate
    print("\nRunning CMC + mAP evaluation ...")
    t0 = time.time()
    metrics = evaluate(query_imgs, gallery_imgs, query_embs, gallery_embs)
    print(f"  Done in {time.time()-t0:.1f}s")

    print("Computing threshold analysis ...")
    thresh = threshold_analysis(query_imgs, gallery_imgs, query_embs, gallery_embs)

    print("Computing per-camera accuracy ...")
    cam_acc = camera_pair_accuracy(query_imgs, gallery_imgs, query_embs, gallery_embs)

    print_report(metrics, thresh, cam_acc, str(duke_root), args)


if __name__ == "__main__":
    main()
