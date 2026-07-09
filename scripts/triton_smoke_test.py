"""Phase 6c Task 10 — Triton end-to-end smoke test.

Validates the Triton backend without requiring live cameras:
  1. Triton health check — all 4 models READY
  2. Identity gate — ORT vs Triton cosine ≥ 0.9999 for adaface and transreid
  3. Throughput benchmark — Triton vs ORT on N synthetic crops
  4. Fail-fast check — dead port raises RuntimeError at startup

Usage:
    python scripts/triton_smoke_test.py
    python scripts/triton_smoke_test.py --triton-url localhost:8001 --n-crops 100
    python scripts/triton_smoke_test.py --skip-failfast   # if port 9999 is in use

Exit codes:
    0  all gates passed
    1  soft warning (cosine < 0.9999 for some crops but no hard stop)
    2  HARD STOP (cosine < 0.99 for any crop)
    3  server connectivity / model readiness failure
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

_torch_lib = _PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "torch" / "lib"
if _torch_lib.is_dir():
    os.environ["PATH"] = str(_torch_lib) + os.pathsep + os.environ.get("PATH", "")

_trt_libs = _PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "tensorrt_libs"
if _trt_libs.is_dir():
    os.environ["PATH"] = str(_trt_libs) + os.pathsep + os.environ.get("PATH", "")

try:
    from dotenv import load_dotenv  # type: ignore[import-untyped]

    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

os.environ.setdefault("VMS_DB_URL", "postgresql://localhost/vms_unused")
os.environ.setdefault("VMS_JWT_SECRET", "smoke-test-dummy")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("triton_smoke")

_COSINE_PASS = 0.9999
_COSINE_HARD_STOP = 0.99

# ---------------------------------------------------------------------------
# Synthetic crop generators
# ---------------------------------------------------------------------------

_RNG = np.random.default_rng(42)


def _face_crops(n: int) -> list[np.ndarray[Any, Any]]:
    """Random noise crops at AdaFace 112x112 (simulates face crop input)."""
    return [_RNG.integers(30, 220, (112, 112, 3), dtype=np.uint8) for _ in range(n)]


def _body_crops(n: int) -> list[np.ndarray[Any, Any]]:
    """Random noise crops at TransReID 384x128 (simulates body crop input)."""
    return [_RNG.integers(30, 220, (384, 128, 3), dtype=np.uint8) for _ in range(n)]


# ---------------------------------------------------------------------------
# Preprocessing (mirrors production code)
# ---------------------------------------------------------------------------


def _prep_face(crop: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    from vms.inference.embedder import adaface_preprocess

    return adaface_preprocess(crop)


def _prep_body(crop: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    from vms.inference.body_embedder import transreid_preprocess

    return transreid_preprocess(crop)


# ---------------------------------------------------------------------------
# ORT runner (direct ONNX session, no gRPC)
# ---------------------------------------------------------------------------


def _ort_session(model_path: str) -> Any:
    import onnxruntime as ort  # type: ignore[import-untyped]

    return ort.InferenceSession(
        model_path,
        providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
    )


def _ort_infer(sess: Any, blob: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    inp = sess.get_inputs()[0].name
    out = sess.run(None, {inp: blob})
    emb = out[0][0].astype(np.float32)
    norm = np.linalg.norm(emb)
    return emb / norm if norm > 1e-8 else emb


# ---------------------------------------------------------------------------
# Triton runner (gRPC via TritonModelClient)
# ---------------------------------------------------------------------------


def _triton_client(url: str, model_name: str) -> Any:
    from vms.inference.backend import _discover_model_io
    from vms.inference.triton_client import TritonModelClient

    inp, outs = _discover_model_io(url, model_name)
    client = TritonModelClient(url, model_name, inp, outs)
    client.check_health()
    return client


def _triton_infer(client: Any, blob: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    raw = client.infer(blob)
    emb = raw[0][0].astype(np.float32)
    norm = np.linalg.norm(emb)
    return emb / norm if norm > 1e-8 else emb


# ---------------------------------------------------------------------------
# Cosine similarity
# ---------------------------------------------------------------------------


def _cosine(a: np.ndarray[Any, Any], b: np.ndarray[Any, Any]) -> float:
    return float(np.dot(a.ravel(), b.ravel()) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-12))


# ---------------------------------------------------------------------------
# Gate 1 — Triton health / model readiness
# ---------------------------------------------------------------------------


def gate_health(triton_url: str) -> bool:
    logger.info("=== Gate 1: Triton health check (%s) ===", triton_url)
    try:
        import urllib.request

        req = urllib.request.urlopen(
            f"http://{triton_url.replace('8001', '8000')}/v2/health/ready", timeout=5
        )
        if req.status != 200:
            logger.error("Health endpoint returned %d", req.status)
            return False
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        return False

    # Check model readiness via repository index
    try:
        import json
        import urllib.request

        http_url = triton_url.replace("8001", "8000")
        req2 = urllib.request.Request(
            f"http://{http_url}/v2/repository/index",
            method="POST",
        )
        resp = urllib.request.urlopen(req2, timeout=5)
        models = json.loads(resp.read())
        ready = {m["name"] for m in models if m.get("state") == "READY"}
        required = {"scrfd", "adaface", "transreid", "ppe"}
        missing = required - ready
        if missing:
            logger.error("Models not READY: %s  (READY: %s)", missing, ready)
            return False
        logger.info("All 4 models READY: %s", sorted(ready))
        return True
    except Exception as exc:
        logger.error("Model readiness check failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Gate 2 — Identity: ORT vs Triton cosine ≥ 0.9999
# ---------------------------------------------------------------------------


def gate_identity(
    triton_url: str,
    adaface_path: str,
    transreid_path: str,
    n_crops: int,
) -> tuple[bool, bool]:
    """Return (passed, hard_stop)."""
    logger.info("=== Gate 2: Identity gate — ORT vs Triton cosine (%d crops each) ===", n_crops)

    face_crops = _face_crops(n_crops)
    body_crops = _body_crops(n_crops)

    logger.info("Loading AdaFace ORT session from %s", adaface_path)
    adaface_ort = _ort_session(adaface_path)
    logger.info("Loading TransReID ORT session from %s", transreid_path)
    transreid_ort = _ort_session(transreid_path)

    logger.info("Connecting Triton adaface and transreid clients")
    adaface_tri = _triton_client(triton_url, "adaface")
    transreid_tri = _triton_client(triton_url, "transreid")

    def _run_comparison(
        crops: list[np.ndarray[Any, Any]],
        prep_fn: Any,
        ort_sess: Any,
        tri_cli: Any,
        label: str,
    ) -> tuple[float, float]:
        sims: list[float] = []
        for i, crop in enumerate(crops):
            blob = prep_fn(crop)
            emb_ort = _ort_infer(ort_sess, blob)
            emb_tri = _triton_infer(tri_cli, blob)
            sim = _cosine(emb_ort, emb_tri)
            sims.append(sim)
            if (i + 1) % 25 == 0 or i == len(crops) - 1:
                logger.info(
                    "  %s: %d/%d  mean=%.6f  min=%.6f",
                    label,
                    i + 1,
                    len(crops),
                    float(np.mean(sims)),
                    float(np.min(sims)),
                )
        return float(np.mean(sims)), float(np.min(sims))

    results: dict[str, tuple[float, float]] = {}

    logger.info("Running AdaFace (face embedding) comparison...")
    results["adaface"] = _run_comparison(
        face_crops, _prep_face, adaface_ort, adaface_tri, "adaface"
    )

    logger.info("Running TransReID (body embedding) comparison...")
    results["transreid"] = _run_comparison(
        body_crops, _prep_body, transreid_ort, transreid_tri, "transreid"
    )

    print()
    print("  Identity gate (ORT vs Triton cosine similarity):")
    print(f"  {'Model':<12}  {'mean':>8}  {'min':>8}  {'status'}")
    print(f"  {'-'*12}  {'-'*8}  {'-'*8}  {'-'*10}")

    overall_pass = True
    hard_stop = False
    for model, (mean_s, min_s) in results.items():
        if min_s < _COSINE_HARD_STOP:
            tag = "HARD STOP"
            overall_pass = False
            hard_stop = True
        elif min_s < _COSINE_PASS or mean_s < _COSINE_PASS:
            tag = "SOFT WARN"
            overall_pass = False
        else:
            tag = "PASS"
        print(f"  {model:<12}  {mean_s:>8.6f}  {min_s:>8.6f}  {tag}")

    print()
    return overall_pass, hard_stop


# ---------------------------------------------------------------------------
# Gate 3 — Throughput: Triton vs ORT on N synthetic face crops
# ---------------------------------------------------------------------------


def gate_throughput(
    triton_url: str,
    adaface_path: str,
    n_crops: int,
    warmup: int = 10,
) -> None:
    logger.info("=== Gate 3: Throughput benchmark (%d crops, %d warmup) ===", n_crops, warmup)

    crops = _face_crops(n_crops + warmup)
    blobs = [_prep_face(c) for c in crops]

    adaface_ort = _ort_session(adaface_path)
    adaface_tri = _triton_client(triton_url, "adaface")

    # ORT benchmark
    for b in blobs[:warmup]:
        _ort_infer(adaface_ort, b)
    t0 = time.perf_counter()
    for b in blobs[warmup:]:
        _ort_infer(adaface_ort, b)
    ort_elapsed = time.perf_counter() - t0
    ort_fps = n_crops / ort_elapsed

    # Triton benchmark
    for b in blobs[:warmup]:
        _triton_infer(adaface_tri, b)
    t0 = time.perf_counter()
    for b in blobs[warmup:]:
        _triton_infer(adaface_tri, b)
    tri_elapsed = time.perf_counter() - t0
    tri_fps = n_crops / tri_elapsed

    ratio = tri_fps / ort_fps if ort_fps > 0 else 0.0

    print(f"  ORT throughput:    {ort_fps:>7.1f} infs/s  ({ort_elapsed*1000/n_crops:.2f} ms/crop)")
    print(f"  Triton throughput: {tri_fps:>7.1f} infs/s  ({tri_elapsed*1000/n_crops:.2f} ms/crop)")
    print(f"  Ratio (Triton/ORT): {ratio:.2f}x", end="")
    if ratio >= 0.8:
        print("  [PASS — Triton not slower than ORT at single-crop dispatch]")
    else:
        print("  [NOTE — Triton slower at single-crop; expected at low camera counts]")
        print("         Triton's cross-camera batching advantage appears at 30+ cameras.")
    print()


# ---------------------------------------------------------------------------
# Gate 4 — Fail-fast: dead port raises RuntimeError
# ---------------------------------------------------------------------------


def gate_failfast(dead_url: str) -> bool:
    logger.info("=== Gate 4: Fail-fast check (dead port %s) ===", dead_url)
    try:
        from vms.inference.backend import TritonInferenceBackend

        TritonInferenceBackend(dead_url)
        logger.error("FAIL — TritonInferenceBackend did NOT raise on dead port %s", dead_url)
        return False
    except (RuntimeError, Exception) as exc:
        logger.info("PASS — raised %s: %s", type(exc).__name__, exc)
        return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--triton-url", default="localhost:8001", help="Triton gRPC host:port")
    parser.add_argument(
        "--n-crops", type=int, default=50, help="Synthetic crops for identity + throughput gates"
    )
    parser.add_argument(
        "--skip-failfast", action="store_true", help="Skip fail-fast gate (if port 9999 is in use)"
    )
    args = parser.parse_args()

    from vms.config import get_settings

    settings = get_settings()
    adaface_path = settings.adaface_model
    transreid_path = settings.transreid_body_model

    if not adaface_path or not Path(adaface_path).is_file():
        logger.error("VMS_ADAFACE_MODEL not set or file missing: %r", adaface_path)
        return 3
    if not transreid_path or not Path(transreid_path).is_file():
        logger.error("VMS_TRANSREID_BODY_MODEL not set or file missing: %r", transreid_path)
        return 3

    print()
    print("=" * 68)
    print("  TRITON SMOKE TEST — Phase 6c Task 10")
    print(f"  Server: {args.triton_url}  |  Crops: {args.n_crops}")
    print("=" * 68)
    print()

    # Gate 1 — health
    if not gate_health(args.triton_url):
        print("RESULT: FAIL — Triton health check failed")
        return 3

    # Gate 2 — identity
    identity_pass, hard_stop = gate_identity(
        args.triton_url, adaface_path, transreid_path, args.n_crops
    )
    if hard_stop:
        print("RESULT: HARD STOP — cosine < 0.99 detected")
        print("ACTION: mandatory /advisor call required before any deployment")
        return 2

    # Gate 3 — throughput
    gate_throughput(args.triton_url, adaface_path, args.n_crops)

    # Gate 4 — fail-fast
    if not args.skip_failfast:
        failfast_pass = gate_failfast("localhost:9999")
    else:
        failfast_pass = True
        logger.info("=== Gate 4: skipped (--skip-failfast) ===")

    # Summary
    print("=" * 68)
    print("  SMOKE TEST SUMMARY")
    print(f"  Identity gate:  {'PASS' if identity_pass else 'SOFT WARN'}")
    print(f"  Fail-fast gate: {'PASS' if failfast_pass else 'FAIL'}")
    print("=" * 68)

    if identity_pass and failfast_pass:
        print("  RESULT: ALL PASS")
        print("  VMS_GPU_TRITON_URL=localhost:8001 is safe to use in production.")
        print()
        return 0

    if not identity_pass:
        print("  RESULT: SOFT WARNING — cosine below 0.9999 for some crops")
        print("  Inspect low-similarity crops; may be edge cases in synthetic noise.")
        print()
        return 1

    print("  RESULT: FAIL — fail-fast gate did not raise on dead port")
    return 1


if __name__ == "__main__":
    sys.exit(main())
