"""Export yolo26m-pose.pt to ONNX for TensorRT EP or runtime flexibility (§6.0.5).

The exported ONNX file is gitignored (models/*.onnx).
Ultralytics writes the output next to the source .pt file by default; use --out to override.

Usage:
    python scripts/export_yolo_onnx.py
    python scripts/export_yolo_onnx.py --model models/yolo26m-pose.pt
    python scripts/export_yolo_onnx.py --model models/yolo26m-pose.pt --out models/yolo26m-pose.onnx

After export, activate via:
    VMS_YOLOV8X_POSE_MODEL=models/yolo26m-pose.onnx
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ORT needs PyTorch CUDA DLLs on Windows — inject the path before importing ultralytics.
_torch_lib = os.path.join(
    os.path.dirname(__file__), "..", "venv", "Lib", "site-packages", "torch", "lib"
)
if os.path.exists(_torch_lib):
    os.environ["PATH"] = os.path.abspath(_torch_lib) + os.pathsep + os.environ.get("PATH", "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export YOLO26m-pose .pt -> .onnx")
    parser.add_argument("--model", default="models/yolo26m-pose.pt", help="Source .pt path")
    parser.add_argument("--out", default="", help="Output .onnx path (default: next to source)")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--opset", type=int, default=17)
    args = parser.parse_args()

    if not os.path.exists(args.model):
        logger.error("Model not found: %s", args.model)
        sys.exit(1)

    from ultralytics import YOLO  # type: ignore[import-untyped]

    model = YOLO(args.model)
    logger.info("Exporting %s to ONNX (imgsz=%d, opset=%d) ...", args.model, args.imgsz, args.opset)
    export_path: str = model.export(
        format="onnx",
        imgsz=args.imgsz,
        opset=args.opset,
        simplify=True,
        dynamic=False,
    )

    if args.out and args.out != export_path:
        import shutil

        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        shutil.move(export_path, args.out)
        export_path = args.out

    if not os.path.exists(export_path):
        logger.error("Export did not produce a file at %s", export_path)
        sys.exit(1)

    logger.info("ONNX export written to: %s", export_path)

    # Numeric validation: run both models on a dummy frame, compare detection counts.
    import numpy as np

    dummy = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)
    r_pt = model(dummy, verbose=False)
    n_pt = len(r_pt[0].boxes) if r_pt[0].boxes is not None else 0

    onnx_model = YOLO(export_path)
    r_onnx = onnx_model(dummy, verbose=False)
    n_onnx = len(r_onnx[0].boxes) if r_onnx[0].boxes is not None else 0

    logger.info("Validation (random noise frame): PT detections=%d  ONNX detections=%d", n_pt, n_onnx)
    if abs(n_pt - n_onnx) > max(2, n_pt // 4):
        logger.warning(
            "Detection count divergence is large (%d vs %d). "
            "Re-validate on a real camera frame before deploying.",
            n_pt,
            n_onnx,
        )

    logger.info("Done. Activate with:  VMS_YOLOV8X_POSE_MODEL=%s", export_path)


if __name__ == "__main__":
    main()
