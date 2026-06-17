"""TransReID ViT-B/16+ICS body Re-ID simulation — threshold calibration script.

Evaluates the TransReID ONNX model on a person Re-ID dataset (Market-1501 or MSMT17)
and recommends production values for reid_body_confirmed_sim / reid_body_cross_cam_sim.

Mirrors scripts/simulate_osnet_reid.py but targets the 768-dim TransReID model
and uses Market-1501 or MSMT17 images (never DukeMTMC — that dataset is retracted).

IMPORTANT — data required (not in repo):
  Market-1501 images: download from the official source, put bounding_box_test/ and
                      query/ under data/market1501/
  MSMT17 images:      similarly under data/msmt17/bounding_box_test/ + query/

IMPORTANT — ONNX model required:
  Run once first: python scripts/export_transreid_onnx.py

Usage:
    python scripts/simulate_transreid_reid.py
    python scripts/simulate_transreid_reid.py --dataset data/market1501
    python scripts/simulate_transreid_reid.py --dataset data/msmt17 --max-query 500
    python scripts/simulate_transreid_reid.py --save-embeddings
    python scripts/simulate_transreid_reid.py --from-cached data/transreid_embeddings
    python scripts/simulate_transreid_reid.py --verify-only models/transreid_body_msmt17.onnx

Requires: onnxruntime (or onnxruntime-gpu), numpy, opencv-python
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
logger = logging.getLogger("simulate_transreid")

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("VMS_DB_URL", "postgresql://localhost/vms_simulate_dummy")
os.environ.setdefault("VMS_JWT_SECRET", "simulate-script-not-a-real-secret")

# TransReID ViT-B/16+ICS input spec (confirmed from checkpoint pos_embed, 2026-06-15)
_INPUT_H = 384
_INPUT_W = 128
_EMBED_DIM = 768
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

# Dataset filename regexes (Market-1501 and MSMT17 both supported)
# Market-1501: 0001_c1s1_001051_00.jpg  -> person=0001, cam=1
# MSMT17:      0001_003_0001_c1s3_100026_00.jpg -> person=0001, cam=1
_MARKET_RE = re.compile(r"^(\d{4})_c(\d)s", re.IGNORECASE)
_MSMT17_RE = re.compile(r"^(\d{4})_\d+_\d+_c(\d)s", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Dataset parsing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _ImgMeta:
    path: Path
    person_id: int
    camera_id: int


def _parse_filename(name: str) -> tuple[int, int] | None:
    """Return (person_id, camera_id) from Market-1501 or MSMT17 filename, or None."""
    m = _MARKET_RE.match(name) or _MSMT17_RE.match(name)
    if not m:
        return None
    pid = int(m.group(1))
    cid = int(m.group(2))
    if pid <= 0:
        return None  # distractor / junk class
    return pid, cid


def parse_folder(folder: Path) -> list[_ImgMeta]:
    out: list[_ImgMeta] = []
    for p in sorted(folder.glob("*.jpg")):
        parsed = _parse_filename(p.name)
        if parsed is None:
            continue
        pid, cid = parsed
        out.append(_ImgMeta(path=p, person_id=pid, camera_id=cid))
    return out


# ---------------------------------------------------------------------------
# TransReID ONNX preprocessing
# ---------------------------------------------------------------------------

def _preprocess_batch(crops_bgr: list[np.ndarray]) -> np.ndarray:  # type: ignore[type-arg]
    """Return (B, 3, H, W) float32 ImageNet-normalised batch from BGR crop list."""
    batch = []
    for bgr in crops_bgr:
        resized = cv2.resize(bgr, (_INPUT_W, _INPUT_H), interpolation=cv2.INTER_LANCZOS4)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        rgb = (rgb - _IMAGENET_MEAN) / _IMAGENET_STD
        batch.append(np.transpose(rgb, (2, 0, 1)))   # (3, H, W)
    return np.stack(batch, axis=0)                    # (B, 3, H, W)


# ---------------------------------------------------------------------------
# Embedding extraction
# ---------------------------------------------------------------------------

def load_session(model_path: str) -> Any:
    try:
        import onnxruntime as ort  # type: ignore[import-untyped]
    except ImportError:
        print("ERROR: onnxruntime not installed. Run: pip install onnxruntime")
        sys.exit(1)

    if not Path(model_path).exists():
        print(f"ERROR: ONNX not found at {model_path}")
        print("  Export first: python scripts/export_transreid_onnx.py")
        sys.exit(1)

    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    sess = ort.InferenceSession(model_path, providers=providers)
    ep = sess.get_providers()[0]
    print(f"  ONNX session: {model_path} (EP: {ep})")
    return sess


def embed_batch(
    sess: Any,
    imgs: list[_ImgMeta],
    batch_size: int = 32,
    desc: str = "",
) -> np.ndarray:  # type: ignore[type-arg]
    """Return (N, 768) float32 L2-normalised embeddings."""
    input_name: str = sess.get_inputs()[0].name
    all_vecs: list[np.ndarray] = []  # type: ignore[type-arg]
    n = len(imgs)
    t0 = time.time()

    for start in range(0, n, batch_size):
        batch_meta = imgs[start : start + batch_size]
        crops = []
        for img in batch_meta:
            bgr = cv2.imread(str(img.path))
            if bgr is None:
                bgr = np.zeros((_INPUT_H, _INPUT_W, 3), dtype=np.uint8)
            crops.append(bgr)

        blob = _preprocess_batch(crops)                 # (B, 3, H, W)
        out = sess.run(None, {input_name: blob})[0]     # (B, 768) L2-normalised
        all_vecs.append(out.astype(np.float32))

        done = min(start + batch_size, n)
        elapsed = time.time() - t0
        eta = elapsed / done * (n - done) if done > 0 else 0
        print(
            f"\r  {desc}: {done}/{n}  ({done/max(elapsed, 1e-6):.0f} img/s  "
            f"ETA {eta:.0f}s)    ",
            end="",
            flush=True,
        )

    print()
    embs = np.concatenate(all_vecs, axis=0)   # (N, 768)

    # Verify ONNX output is already L2-normalised (sanity guard)
    sample_norms = np.linalg.norm(embs[:10], axis=1)
    if not np.allclose(sample_norms, 1.0, atol=0.02):
        logger.warning("ONNX output norms not ~1.0: %s — re-normalising", sample_norms)
        norms = np.linalg.norm(embs, axis=1, keepdims=True) + 1e-8
        embs = embs / norms

    return embs


# ---------------------------------------------------------------------------
# Standard Re-ID evaluation (CMC + mAP) — identical protocol to OSNet script
# ---------------------------------------------------------------------------

def evaluate(
    query_imgs: list[_ImgMeta],
    gallery_imgs: list[_ImgMeta],
    query_embs: np.ndarray,    # (Nq, 768)
    gallery_embs: np.ndarray,  # (Ng, 768)
    top_k: tuple[int, ...] = (1, 5, 10),
) -> dict[str, float]:
    """CMC@k + mAP with standard same-camera junk exclusion."""
    sim_matrix: np.ndarray = query_embs @ gallery_embs.T  # (Nq, Ng)

    cmc_hits = {k: 0 for k in top_k}
    ap_sum = 0.0
    n_valid = 0

    gallery_pids = np.array([g.person_id for g in gallery_imgs], dtype=np.int32)
    gallery_cids = np.array([g.camera_id for g in gallery_imgs], dtype=np.int32)

    for qi, qmeta in enumerate(query_imgs):
        sims = sim_matrix[qi]
        junk = (gallery_pids == qmeta.person_id) & (gallery_cids == qmeta.camera_id)
        pos  = (gallery_pids == qmeta.person_id) & (gallery_cids != qmeta.camera_id)

        if pos.sum() == 0:
            continue
        n_valid += 1

        order = np.argsort(-sims)
        keep = ~junk[order]
        ranked_pos = pos[order][keep]

        cum = np.cumsum(ranked_pos)
        for k in top_k:
            if cum[min(k, len(cum)) - 1] >= 1:
                cmc_hits[k] += 1

        n_pos = int(pos.sum())
        hit_at_r = np.cumsum(ranked_pos).astype(float)
        r = np.arange(1, len(ranked_pos) + 1, dtype=float)
        precision_at_r = hit_at_r / r
        ap_sum += float(np.sum(precision_at_r * ranked_pos)) / n_pos

    results: dict[str, float] = {}
    for k in top_k:
        results[f"rank{k}"] = cmc_hits[k] / max(n_valid, 1) * 100.0
    results["mAP"] = ap_sum / max(n_valid, 1) * 100.0
    results["n_valid_queries"] = float(n_valid)
    return results


# ---------------------------------------------------------------------------
# Threshold analysis — same logic as OSNet script
# ---------------------------------------------------------------------------

def threshold_analysis(
    query_imgs: list[_ImgMeta],
    gallery_imgs: list[_ImgMeta],
    query_embs: np.ndarray,
    gallery_embs: np.ndarray,
) -> dict[str, Any]:
    """Cosine similarity distributions → production threshold recommendations."""
    rng = np.random.default_rng(42)
    gallery_pids = np.array([g.person_id for g in gallery_imgs], dtype=np.int32)
    gallery_cids = np.array([g.camera_id for g in gallery_imgs], dtype=np.int32)

    same_sims: list[float] = []
    diff_sims: list[float] = []

    for qi in rng.choice(len(query_imgs), size=min(500, len(query_imgs)), replace=False):
        qmeta = query_imgs[qi]
        sims = query_embs[qi] @ gallery_embs.T

        pos_idx = np.where(
            (gallery_pids == qmeta.person_id) & (gallery_cids != qmeta.camera_id)
        )[0]
        for idx in pos_idx[:10]:
            same_sims.append(float(sims[idx]))

        neg_idx = np.where(gallery_pids != qmeta.person_id)[0]
        for idx in rng.choice(neg_idx, size=min(20, len(neg_idx)), replace=False):
            diff_sims.append(float(sims[idx]))

    s = np.array(same_sims, dtype=np.float32)
    d = np.array(diff_sims, dtype=np.float32)

    def pct(arr: np.ndarray, q: float) -> float:
        return float(np.percentile(arr, q))

    threshold_conservative = pct(s, 5)    # 95% recall
    threshold_loose = pct(s, 1)           # ~99% recall
    threshold_fp1 = pct(d, 99)            # 1% FP rate
    recommended = max(threshold_conservative, threshold_fp1) - 0.02

    return {
        "same_person": {
            "n": len(s),
            "min": float(s.min()),
            "p1": pct(s, 1), "p5": pct(s, 5), "p25": pct(s, 25),
            "median": pct(s, 50), "p75": pct(s, 75), "p95": pct(s, 95),
            "max": float(s.max()),
        },
        "diff_person": {
            "n": len(d),
            "min": float(d.min()),
            "median": pct(d, 50), "p95": pct(d, 95), "p99": pct(d, 99),
            "max": float(d.max()),
        },
        "threshold_conservative": threshold_conservative,
        "threshold_loose": threshold_loose,
        "threshold_fp1pct": threshold_fp1,
        "recommended": recommended,
    }


def camera_pair_accuracy(
    query_imgs: list[_ImgMeta],
    gallery_imgs: list[_ImgMeta],
    query_embs: np.ndarray,
    gallery_embs: np.ndarray,
) -> dict[str, float]:
    gallery_pids = np.array([g.person_id for g in gallery_imgs], dtype=np.int32)
    gallery_cids = np.array([g.camera_id for g in gallery_imgs], dtype=np.int32)
    hits: dict[str, int] = defaultdict(int)
    total: dict[str, int] = defaultdict(int)
    sim_matrix = query_embs @ gallery_embs.T

    for qi, qmeta in enumerate(query_imgs):
        sims = sim_matrix[qi]
        junk = (gallery_pids == qmeta.person_id) & (gallery_cids == qmeta.camera_id)
        pos  = (gallery_pids == qmeta.person_id) & (gallery_cids != qmeta.camera_id)
        if pos.sum() == 0:
            continue
        order = np.argsort(-sims)
        keep = ~junk[order]
        ranked_pos = pos[order][keep]
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
    w = "=" * 64
    print(f"\n{w}")
    print("  TransReID ViT-B/16+ICS msmt17 -- BODY Re-ID BENCHMARK")
    print(w)
    print(f"  Dataset  : {dataset_path}")
    print(f"  Model    : {args.model}")
    print(f"  Queries  : {int(metrics['n_valid_queries'])}")
    print(f"  Embed dim: {_EMBED_DIM}  Input: {_INPUT_H}x{_INPUT_W}")
    print()

    print("  --- CMC Accuracy -------------------------------------------")
    print(f"  Rank-1  : {metrics['rank1']:6.2f}%")
    print(f"  Rank-5  : {metrics['rank5']:6.2f}%")
    print(f"  Rank-10 : {metrics['rank10']:6.2f}%")
    print(f"  mAP     : {metrics['mAP']:6.2f}%")
    print()

    print("  --- Cosine Similarity Distribution -------------------------")
    s = thresh["same_person"]
    d = thresh["diff_person"]
    print(f"  Same person (cross-cam)   n={s['n']}")
    print(f"    p1={s['p1']:.3f}  p5={s['p5']:.3f}  p25={s['p25']:.3f}"
          f"  median={s['median']:.3f}  p75={s['p75']:.3f}  p95={s['p95']:.3f}")
    print(f"  Different person          n={d['n']}")
    print(f"    median={d['median']:.3f}  p95={d['p95']:.3f}  p99={d['p99']:.3f}"
          f"  max={d['max']:.3f}")
    print()

    print("  --- Per-Camera Rank-1 --------------------------------------")
    for cam, acc in sorted(cam_accuracy.items()):
        bar_len = int(acc / 2)
        bar = "#" * bar_len + "." * (50 - bar_len)
        print(f"  {cam}: {acc:5.1f}%  |{bar}|")
    print()

    sep = s["p5"] - d["p99"]
    print("  --- Production Threshold Recommendations ------------------")
    print(f"  Separation gap (same-p5 vs diff-p99): {sep:.3f}")
    print(f"    ({s['p5']:.3f} same-p5  vs  {d['p99']:.3f} diff-p99)")
    if sep < 0.05:
        print("  WARNING: small gap (<0.05) -- models may need domain adaptation")
    print()
    print(f"  Conservative (95% recall):  reid_body_confirmed_sim = {thresh['threshold_conservative']:.2f}")
    print(f"  Recommended  (balanced):    reid_body_confirmed_sim = {thresh['recommended']:.2f}")
    print(f"  Loose        (~99% recall): reid_body_confirmed_sim = {thresh['threshold_loose']:.2f}")
    print()
    print("  Add 0.05 for reid_body_cross_cam_sim in each case.")
    print()
    print("  Current config.py defaults (OSNet-calibrated, NOT valid for TransReID):")
    print("    reid_body_confirmed_sim = 0.51")
    print("    reid_body_cross_cam_sim = 0.56")
    print()
    print("  MANDATORY: run /advisor before changing these thresholds (CLAUDE.md S0.5).")
    print(w)
    print()
    print("  Next steps:")
    print("    1. Record the 'Recommended' value above")
    print("    2. Run /advisor with this output to approve the new threshold")
    print("    3. Update VMS_REID_BODY_CONFIRMED_SIM and VMS_REID_BODY_CROSS_CAM_SIM")
    print("    4. Swap BodyEmbedder -> TransReIDBodyEmbedder in the engine")
    print(f"{w}\n")


# ---------------------------------------------------------------------------
# Verify-only mode: quick ONNX shape/norm check without dataset
# ---------------------------------------------------------------------------

def verify_onnx(model_path: str) -> None:
    sess = load_session(model_path)
    input_name = sess.get_inputs()[0].name
    dummy = np.random.randn(2, 3, _INPUT_H, _INPUT_W).astype(np.float32)
    out = sess.run(None, {input_name: dummy})[0]
    norms = np.linalg.norm(out, axis=1)
    print(f"Output shape: {out.shape}")
    print(f"Output norms: {norms}  (expected ~1.0 each)")
    assert out.shape == (2, _EMBED_DIM), f"expected (2,{_EMBED_DIM}), got {out.shape}"
    assert np.allclose(norms, 1.0, atol=0.02), f"embeddings not L2-normalised: {norms}"
    print("ONNX verify: PASSED")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dataset", default=str(REPO_ROOT / "data" / "market1501"),
        help="Dataset root containing query/ and bounding_box_test/ (Market-1501 or MSMT17)",
    )
    parser.add_argument(
        "--model", default=str(REPO_ROOT / "models" / "transreid_body_msmt17.onnx"),
        help="TransReID ONNX path (export first: python scripts/export_transreid_onnx.py)",
    )
    parser.add_argument("--max-query", type=int, default=0,
                        help="Limit query count (0=all). Use 500 for a quick test.")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument(
        "--save-embeddings", action="store_true",
        help="Cache 768-dim embeddings to data/transreid_embeddings/ for re-runs",
    )
    parser.add_argument(
        "--from-cached", metavar="DIR",
        help="Skip embedding computation; load pre-cached .npy files from DIR",
    )
    parser.add_argument(
        "--verify-only", metavar="ONNX",
        help="Only verify the ONNX model (shape + norm check); do not run evaluation",
    )
    args = parser.parse_args()

    if args.verify_only:
        verify_onnx(args.verify_only)
        return

    dataset_root = Path(args.dataset)
    query_dir   = dataset_root / "query"
    gallery_dir = dataset_root / "bounding_box_test"

    if not query_dir.exists() or not gallery_dir.exists():
        print(f"ERROR: dataset not found at {dataset_root}")
        print(f"  Expected: {query_dir}/  and  {gallery_dir}/")
        print()
        print("  Download Market-1501 from the official source and extract to:")
        print(f"    {dataset_root}/")
        print()
        print("  For MSMT17, extract to data/msmt17/ and pass --dataset data/msmt17")
        print()
        print("  NOTE: DukeMTMC-reID is legally retracted — do NOT use it.")
        sys.exit(1)

    print(f"Dataset: {dataset_root}")
    print("Parsing image metadata ...")
    query_imgs   = parse_folder(query_dir)
    gallery_imgs = parse_folder(gallery_dir)

    if not query_imgs:
        print(f"ERROR: no parseable images in {query_dir}")
        print("  Check filenames match Market-1501 (PPPP_cNsS_*.jpg) or MSMT17 pattern.")
        sys.exit(1)

    print(f"  Query  : {len(query_imgs)} images")
    print(f"  Gallery: {len(gallery_imgs)} images")

    if args.max_query > 0:
        query_imgs = query_imgs[: args.max_query]
        print(f"  Limited to {len(query_imgs)} queries (--max-query {args.max_query})")

    cache_dir = REPO_ROOT / "data" / "transreid_embeddings"
    q_cache = cache_dir / f"query_{len(query_imgs)}.npy"
    g_cache = cache_dir / f"gallery_{len(gallery_imgs)}.npy"

    if args.from_cached:
        from_dir = Path(args.from_cached)
        q_cache_load = from_dir / f"query_{len(query_imgs)}.npy"
        g_cache_load = from_dir / f"gallery_{len(gallery_imgs)}.npy"
        if not q_cache_load.exists() or not g_cache_load.exists():
            print(f"ERROR: cached embeddings not found in {from_dir}")
            print(f"  Run with --save-embeddings first to generate them.")
            sys.exit(1)
        print(f"Loading cached embeddings from {from_dir} ...")
        query_embs   = np.load(str(q_cache_load))
        gallery_embs = np.load(str(g_cache_load))
        print(f"  query_embs: {query_embs.shape}  gallery_embs: {gallery_embs.shape}")
    else:
        sess = load_session(args.model)
        print(f"\nComputing query embeddings ({len(query_imgs)} images) ...")
        query_embs = embed_batch(sess, query_imgs, args.batch_size, "Query  ")

        print(f"Computing gallery embeddings ({len(gallery_imgs)} images) ...")
        gallery_embs = embed_batch(sess, gallery_imgs, args.batch_size, "Gallery")

        if args.save_embeddings:
            cache_dir.mkdir(parents=True, exist_ok=True)
            np.save(str(q_cache), query_embs)
            np.save(str(g_cache), gallery_embs)
            print(f"  Embeddings saved to {cache_dir}")

    print("\nRunning CMC + mAP evaluation ...")
    t0 = time.time()
    metrics = evaluate(query_imgs, gallery_imgs, query_embs, gallery_embs)
    print(f"  Done in {time.time() - t0:.1f}s")

    print("Computing threshold analysis ...")
    thresh = threshold_analysis(query_imgs, gallery_imgs, query_embs, gallery_embs)

    print("Computing per-camera accuracy ...")
    cam_acc = camera_pair_accuracy(query_imgs, gallery_imgs, query_embs, gallery_embs)

    print_report(metrics, thresh, cam_acc, str(dataset_root), args)


if __name__ == "__main__":
    main()
