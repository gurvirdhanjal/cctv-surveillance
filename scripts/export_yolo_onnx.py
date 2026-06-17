"""Export YOLO26m-pose.pt to ONNX (§6.0.5).

Follows the official Ultralytics export pattern exactly.
The .onnx file lands next to the source .pt; use --out to override.

Usage:
    python scripts/export_yolo_onnx.py
    python scripts/export_yolo_onnx.py --model models/yolo26m-pose.pt
    python scripts/export_yolo_onnx.py --model models/yolo26m-pose.pt --out models/yolo26m-pose.onnx

After export, activate via:
    VMS_YOLOV8X_POSE_MODEL=models/yolo26m-pose.onnx

For production on RTX 2000 Ada, prefer the TRT engine:
    python scripts/export_yolo_trt.py
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


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
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        shutil.move(export_path, args.out)
        export_path = args.out

    if not os.path.exists(export_path):
        logger.error("Export did not produce a file at %s", export_path)
        sys.exit(1)

    logger.info("Done. ONNX written to: %s", export_path)
    logger.info("Activate with:  VMS_YOLOV8X_POSE_MODEL=%s", export_path)


if __name__ == "__main__":
    main()
