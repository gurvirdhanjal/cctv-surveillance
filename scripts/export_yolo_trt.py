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
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ORT / CUDA DLL path injection for Windows (same as multi_cam_pipeline_test.py).
_torch_lib = os.path.join(
    os.path.dirname(__file__), "..", "venv", "Lib", "site-packages", "torch", "lib"
)
if os.path.exists(_torch_lib):
    os.environ["PATH"] = os.path.abspath(_torch_lib) + os.pathsep + os.environ.get("PATH", "")


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

    if not os.path.exists(export_path):
        logger.error("TRT export did not produce a file at %s", export_path)
        sys.exit(1)

    size_mb = os.path.getsize(export_path) / (1024 * 1024)
    logger.info("TensorRT engine written to: %s (%.1f MB)", export_path, size_mb)
    logger.info("Done. Activate with:  VMS_YOLOV8X_POSE_MODEL=%s", export_path)
    logger.info(
        "Also set:  VMS_GPU_TENSORRT_ENABLED=true  VMS_DETECTOR_INTERVAL_FRAMES=2"
    )


if __name__ == "__main__":
    main()
