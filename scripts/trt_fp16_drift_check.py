"""TRT FP16 cosine-drift check -- identity correctness gate (Phase 6b Task 3).

Loads AdaFace and TransReID body embedder twice on the same crop set:
  1. CUDAExecutionProvider  -> FP32 reference embedding
  2. TensorrtExecutionProvider (FP16) -> production embedding

Reports pairwise cosine similarity between FP32 and FP16 for each crop.

Pass criterion  : mean cosine similarity >= 0.999 AND min >= 0.995.
Hard-stop zone  : any crop below 0.99 -> exit 2; do NOT enable FP16 on that
                  model without a mandatory /advisor call (CLAUDE.md ss0.5).
Soft-warning    : min in [0.99, 0.995) -> exit 1; investigate before shipping.
Full pass       : both models pass -> exit 0.

Usage
-----
    # Both models (recommended):
    python scripts/trt_fp16_drift_check.py \\
        --face-crops scripts/test_crops/faces/ \\
        --body-crops scripts/test_crops/bodies/

    # Face only or body only:
    python scripts/trt_fp16_drift_check.py --face-crops /path/to/faces/
    python scripts/trt_fp16_drift_check.py --body-crops /path/to/bodies/

Collecting crops
----------------
    Run multi_cam_pipeline_test.py in --calibration mode, then use the
    snapshot key (S) to save frames.  Extract face/body crops manually or
    with scripts/extract_crops.py (if present).

    Minimum: 50 face crops + 50 body crops for a meaningful min statistic.
    More is better; 200+ each gives a stable distribution tail.

First-run note
--------------
    The TensorRT EP builds engine files the first time each model is loaded.
    This takes 2-5 minutes per model on RTX 2000 Ada.  Subsequent runs load
    from the cache (VMS_GPU_TENSORRT_ENGINE_CACHE_DIR).  The script logs a
    warning before each TRT load so you know to wait.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import cv2
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Prepend PyTorch CUDA DLLs so onnxruntime-gpu can find cublasLt.
_torch_lib = _PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "torch" / "lib"
if _torch_lib.is_dir():
    os.environ["PATH"] = str(_torch_lib) + os.pathsep + os.environ.get("PATH", "")

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

# Satisfy settings validation without a real DB.
os.environ.setdefault("VMS_DB_URL", "postgresql://localhost/vms_unused")
os.environ.setdefault("VMS_JWT_SECRET", "drift-check-dummy-secret")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger("drift_check")

# -- thresholds ----------------------------------------------------------------

_PASS_MEAN = 0.999  # mean cosine similarity required across all crops
_PASS_MIN = 0.995  # minimum per-crop cosine similarity for a soft pass
_HARD_STOP_MIN = 0.99  # any crop below this -> hard stop, do not ship FP16

# -- preprocessing (mirrors production embedder code exactly) ------------------

# AdaFace (embedder.py): 112x112 RGB, (pixel-127.5)/127.5
_ADAFACE_SIZE = 112


def _preprocess_face(img_bgr: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    resized = cv2.resize(img_bgr, (_ADAFACE_SIZE, _ADAFACE_SIZE), interpolation=cv2.INTER_LINEAR)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
    rgb = (rgb - 127.5) / 127.5
    return np.transpose(rgb, (2, 0, 1))[None]  # type: ignore[return-value]  # (1, 3, 112, 112)


# TransReID (body_embedder.py): 128Wx384H RGB, ImageNet norm
_REID_H, _REID_W = 384, 128
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _preprocess_body(img_bgr: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    resized = cv2.resize(img_bgr, (_REID_W, _REID_H), interpolation=cv2.INTER_LANCZOS4)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    rgb = (rgb - _IMAGENET_MEAN) / _IMAGENET_STD
    return np.transpose(rgb, (2, 0, 1))[None]  # type: ignore[return-value]  # (1, 3, 384, 128)


# -- session loading -----------------------------------------------------------


def _load_session(model_path: str, providers: list[Any], label: str) -> Any:
    """Load an ORT InferenceSession; return it or raise on failure."""
    import onnxruntime as ort  # type: ignore[import-untyped]

    first = providers[0]
    first_name = first[0] if isinstance(first, tuple) else first
    logger.info("Loading %s with provider: %s", label, first_name)
    sess = ort.InferenceSession(model_path, providers=providers)
    active = sess.get_providers()
    expected: str = first[0] if isinstance(first, tuple) else first
    if active[0] != expected:
        logger.warning(
            "%s: requested %s but active provider is %s -- TRT EP may have "
            "fallen back (unsupported op or engine build failure)",
            label,
            expected,
            active[0],
        )
    else:
        logger.info("%s: active provider confirmed: %s", label, active[0])
    return sess


def _trt_providers(cache_dir: str, fp16: bool) -> list[Any]:
    from vms.config import get_settings

    settings = get_settings()
    trt_opts: dict[str, Any] = {
        "trt_engine_cache_enable": True,
        "trt_engine_cache_path": cache_dir,
        "trt_fp16_enable": fp16,
        "trt_max_workspace_size": settings.gpu_tensorrt_workspace_mb * 1024 * 1024,
    }
    return [
        ("TensorrtExecutionProvider", trt_opts),
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ]


def _cuda_providers() -> list[str]:
    return ["CUDAExecutionProvider", "CPUExecutionProvider"]


# -- embedding + cosine similarity ---------------------------------------------


def _embed(sess: Any, blob: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """Run one forward pass; return L2-normalised 1-D embedding."""
    input_name: str = sess.get_inputs()[0].name
    raw: list[Any] = sess.run(None, {input_name: blob})
    emb = np.array(raw[0][0], dtype=np.float32)
    norm = float(np.linalg.norm(emb))
    return emb / norm if norm > 1e-8 else emb  # type: ignore[return-value]


def _cosine(a: np.ndarray[Any, Any], b: np.ndarray[Any, Any]) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


# -- per-model drift runner ----------------------------------------------------


def _run_drift(
    model_path: str,
    crops: list[np.ndarray[Any, Any]],
    preprocess_fn: Callable[[np.ndarray[Any, Any]], np.ndarray[Any, Any]],
    label: str,
    cache_dir: str,
    fp16: bool,
) -> tuple[float, float, bool]:
    """Return (mean_sim, min_sim, passed) for one model vs its FP32 baseline."""
    logger.info("--- %s: loading FP32 reference (CUDA EP) ---", label)
    sess_fp32 = _load_session(model_path, _cuda_providers(), f"{label}/FP32")

    logger.info(
        "--- %s: loading FP16 TRT EP --- (first run builds engine; may take 2-5 min) ---",
        label,
    )
    sess_fp16 = _load_session(model_path, _trt_providers(cache_dir, fp16), f"{label}/TRT-FP16")

    # TRT warm-up: first inference triggers JIT engine compilation on the TRT session.
    dummy = preprocess_fn(np.zeros((64, 32, 3), dtype=np.uint8))
    logger.info("%s: running TRT warm-up pass...", label)
    _embed(sess_fp32, dummy)
    _embed(sess_fp16, dummy)
    logger.info("%s: warm-up complete", label)

    sims: list[float] = []
    for i, crop in enumerate(crops):
        blob = preprocess_fn(crop)
        emb32 = _embed(sess_fp32, blob)
        emb16 = _embed(sess_fp16, blob)
        sim = _cosine(emb32, emb16)
        sims.append(sim)
        if (i + 1) % 25 == 0:
            logger.info(
                "%s: %d/%d crops -- running mean=%.4f  running min=%.4f",
                label,
                i + 1,
                len(crops),
                float(np.mean(sims)),
                float(np.min(sims)),
            )

    mean_sim = float(np.mean(sims))
    min_sim = float(np.min(sims))

    if min_sim < _HARD_STOP_MIN:
        status = "HARD STOP"
        passed = False
    elif min_sim < _PASS_MIN or mean_sim < _PASS_MEAN:
        status = "SOFT WARN"
        passed = False
    else:
        status = "PASS"
        passed = True

    logger.info(
        "[%s] %s  FP16 drift: mean=%.4f  min=%.4f  n=%d  -> %s",
        label,
        "PASS" if passed else "FAIL",
        mean_sim,
        min_sim,
        len(sims),
        status,
    )
    return mean_sim, min_sim, passed


# -- crop loading --------------------------------------------------------------


def _load_crops(directory: str, label: str) -> list[np.ndarray[Any, Any]]:
    crops: list[np.ndarray[Any, Any]] = []
    path = Path(directory)
    if not path.is_dir():
        logger.error("%s directory not found: %s", label, directory)
        return crops
    for f in sorted(path.iterdir()):
        if f.suffix.lower() in {".jpg", ".jpeg", ".png"}:
            img = cv2.imread(str(f))
            if img is not None and img.size > 0:
                crops.append(img)
    logger.info("Loaded %d %s crops from %s", len(crops), label, directory)
    if len(crops) < 10:
        logger.warning(
            "%s: only %d crops -- results may not be statistically stable; " "50+ recommended",
            label,
            len(crops),
        )
    return crops


# -- main ----------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="TRT FP16 cosine-drift check")
    parser.add_argument("--face-crops", default="", help="Directory of face crop images (JPG/PNG)")
    parser.add_argument("--body-crops", default="", help="Directory of body crop images (JPG/PNG)")
    parser.add_argument(
        "--no-fp16",
        action="store_true",
        help="Use FP32 TRT (smoke test only -- validates TRT EP loads, not FP16 drift)",
    )
    args = parser.parse_args()

    if not args.face_crops and not args.body_crops:
        parser.error("Provide at least one of --face-crops or --body-crops")

    from vms.config import get_settings

    settings = get_settings()

    cache_dir = settings.gpu_tensorrt_engine_cache_dir
    os.makedirs(cache_dir, exist_ok=True)
    fp16 = not args.no_fp16

    results: dict[str, tuple[float, float, bool]] = {}

    # -- AdaFace ---------------------------------------------------------------
    if args.face_crops:
        face_model = settings.adaface_model
        if not face_model or not os.path.isfile(face_model):
            logger.error(
                "AdaFace ONNX not found at %r -- set VMS_ADAFACE_MODEL in .env", face_model
            )
        else:
            crops = _load_crops(args.face_crops, "face")
            if crops:
                mean_s, min_s, passed = _run_drift(
                    face_model, crops, _preprocess_face, "AdaFace", cache_dir, fp16
                )
                results["AdaFace"] = (mean_s, min_s, passed)

    # -- TransReID body --------------------------------------------------------
    if args.body_crops:
        body_model = settings.transreid_body_model
        if not body_model or not os.path.isfile(body_model):
            logger.error(
                "TransReID ONNX not found at %r -- set VMS_TRANSREID_BODY_MODEL in .env",
                body_model,
            )
        else:
            crops = _load_crops(args.body_crops, "body")
            if crops:
                mean_s, min_s, passed = _run_drift(
                    body_model, crops, _preprocess_body, "TransReID", cache_dir, fp16
                )
                results["TransReID"] = (mean_s, min_s, passed)

    if not results:
        logger.error("No models could be evaluated -- check model paths and crop directories")
        return 3

    # -- summary ---------------------------------------------------------------
    print()
    print("=" * 68)
    print("  TRT FP16 DRIFT CHECK SUMMARY")
    print(f"  Pass criteria: mean >= {_PASS_MEAN}  |  min >= {_PASS_MIN}")
    print(f"  Hard-stop zone: any crop < {_HARD_STOP_MIN}")
    print("=" * 68)

    overall_pass = True
    hard_stop = False
    for model_name, (mean_s, min_s, passed) in results.items():
        if min_s < _HARD_STOP_MIN:
            tag = "HARD STOP"
        elif not passed:
            tag = "SOFT WARN"
        else:
            tag = "PASS"
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}] {model_name:<12}  mean={mean_s:.4f}  min={min_s:.4f}  [{tag}]")
        if not passed:
            overall_pass = False
        if min_s < _HARD_STOP_MIN:
            hard_stop = True

    print("=" * 68)
    if overall_pass:
        print("  RESULT: ALL PASS -- safe to enable VMS_GPU_TENSORRT_ENABLED=true")
        print("  NOTE: keep all reid_*/adaface_* thresholds frozen (CLAUDE.md ss0.5)")
    elif hard_stop:
        print("  RESULT: HARD STOP -- do NOT enable FP16 on failing model(s)")
        print("  ACTION: raise mandatory /advisor call before any threshold change")
    else:
        print("  RESULT: SOFT WARNING -- investigate min outliers before shipping")
        print("  ACTION: inspect the lowest-similarity crops; may be noisy inputs")
    print("=" * 68)
    print()

    if hard_stop:
        return 2
    if not overall_pass:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
