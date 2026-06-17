"""Export yolo26m-pose (.pt or .onnx) to a TensorRT engine for maximum GPU throughput (§6.1).

YOLO26m-pose: equal accuracy to yolov8x-pose (~69 mAP), 2x faster on TRT (5ms vs ~10ms T4).
RTX 2000 Ada Gen (compute cap 8.9) has strong FP16 support; --fp16 is the default.
The .engine file is gitignored. Engine build takes 2-5 minutes the first run; Ultralytics
caches it and subsequent loads are instant.

Usage:
    python scripts/export_yolo_trt.py
    python scripts/export_yolo_trt.py --model models/yolo26m-pose.pt --fp16
    python scripts/export_yolo_trt.py --model models/yolo26m-pose.onnx

After export, activate via:
    VMS_YOLOV8X_POSE_MODEL=models/yolo26m-pose.engine

Note: the TRT engine is tied to the exact GPU architecture + driver version it was built on.
Rebuild after driver upgrades or when moving the model to a different GPU.

TensorRT Python package is required. If missing, this script attempts auto-install from
NVIDIA's PyPI index. If that also fails, trtexec (TensorRT CLI) is used as a fallback.
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import shutil
import subprocess
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ORT / CUDA DLL path injection for Windows.
_torch_lib = os.path.join(
    os.path.dirname(__file__), "..", "venv", "Lib", "site-packages", "torch", "lib"
)
if os.path.exists(_torch_lib):
    os.environ["PATH"] = os.path.abspath(_torch_lib) + os.pathsep + os.environ.get("PATH", "")


def _ensure_tensorrt() -> bool:
    """Try to import tensorrt; attempt pip install if missing. Returns True if available."""
    try:
        import tensorrt  # type: ignore[import-untyped]

        _ = tensorrt  # confirm importable; not used beyond this check
        return True
    except ImportError:
        pass

    logger.info("tensorrt Python package not found — attempting pip install from NVIDIA index ...")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "tensorrt",
            "--extra-index-url",
            "https://pypi.nvidia.com",
            "--quiet",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        try:
            import tensorrt  # type: ignore[import-untyped]

            _ = tensorrt
            logger.info("tensorrt installed successfully")
            return True
        except ImportError:
            pass

    logger.warning(
        "pip install tensorrt failed: %s", result.stderr.strip() or result.stdout.strip()
    )
    return False


def _find_trtexec() -> str:
    """Return path to trtexec binary or empty string if not found."""
    found = shutil.which("trtexec")
    if found:
        return found
    # Common Windows TensorRT install locations
    patterns = [
        r"C:\Program Files\NVIDIA GPU Computing Toolkit\TensorRT-*\bin\trtexec.exe",
        r"C:\TensorRT-*\bin\trtexec.exe",
        r"C:\tools\TensorRT-*\bin\trtexec.exe",
    ]
    for pattern in patterns:
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[-1]  # latest version
    return ""


def _build_via_trtexec(onnx_path: str, engine_path: str, fp16: bool) -> None:
    trtexec = _find_trtexec()
    if not trtexec:
        logger.error(
            "Neither the 'tensorrt' Python package nor 'trtexec' was found.\n"
            "\n"
            "Fix options (choose one):\n"
            "  1. pip install tensorrt --extra-index-url https://pypi.nvidia.com\n"
            "  2. Download TensorRT from https://developer.nvidia.com/tensorrt\n"
            "     then add <TensorRT>/bin to PATH and re-run this script.\n"
            "  3. Use the ONNX model directly (no engine build needed):\n"
            "     VMS_YOLOV8X_POSE_MODEL=%s",
            onnx_path,
        )
        sys.exit(1)

    logger.info("Using trtexec at %s", trtexec)
    cmd = [trtexec, f"--onnx={onnx_path}", f"--saveEngine={engine_path}"]
    if fp16:
        cmd.append("--fp16")
    logger.info("Running: %s", " ".join(cmd))
    logger.info("This takes 2-5 minutes on first run.")
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export YOLO26m-pose -> TensorRT .engine")
    parser.add_argument(
        "--model",
        default="models/yolo26m-pose.pt",
        help="Source .pt or .onnx path",
    )
    parser.add_argument(
        "--fp16",
        action="store_true",
        default=True,
        help="Enable FP16 (recommended for Ada/Ampere/Turing GPUs)",
    )
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", type=int, default=0, help="CUDA device index")
    args = parser.parse_args()

    if not os.path.exists(args.model):
        logger.error("Model not found: %s", args.model)
        sys.exit(1)

    # Derive expected ONNX source (needed for trtexec fallback path).
    if args.model.endswith(".onnx"):
        onnx_src = args.model
    else:
        onnx_src = os.path.splitext(args.model)[0] + ".onnx"

    engine_out = os.path.splitext(args.model)[0] + ".engine"

    if _ensure_tensorrt():
        # Ultralytics path — handles .pt and .onnx, builds engine internally.
        from ultralytics import YOLO  # type: ignore[import-untyped]

        model = YOLO(args.model)
        logger.info(
            "Building TensorRT engine from %s (fp16=%s, device=%d) ...",
            args.model,
            args.fp16,
            args.device,
        )
        logger.info("This takes 2-5 minutes on first run. The engine is cached after.")
        export_path: str = model.export(
            format="engine",
            imgsz=args.imgsz,
            half=args.fp16,
            device=args.device,
            simplify=True,
        )
    else:
        # trtexec fallback — requires ONNX source.
        if not os.path.exists(onnx_src):
            logger.error(
                "ONNX source not found at %s — run export_yolo_onnx.py first, then retry.",
                onnx_src,
            )
            sys.exit(1)
        _build_via_trtexec(onnx_src, engine_out, args.fp16)
        export_path = engine_out

    if not os.path.exists(export_path):
        logger.error("TRT export did not produce a file at %s", export_path)
        sys.exit(1)

    size_mb = os.path.getsize(export_path) / (1024 * 1024)
    logger.info("TensorRT engine written to: %s (%.1f MB)", export_path, size_mb)
    logger.info("Done. Activate with:  VMS_YOLOV8X_POSE_MODEL=%s", export_path)
    logger.info("Also set:  VMS_GPU_TENSORRT_ENABLED=true  VMS_DETECTOR_INTERVAL_FRAMES=2")


if __name__ == "__main__":
    main()
