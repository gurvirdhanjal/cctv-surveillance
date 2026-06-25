"""YOLOv8l SH17 PPE detection model (ONNX).

Detects PPE items inside a person-crop using a YOLOv8l model trained on the
SH17 dataset (17 classes).

Model input:  (1, 3, 640, 640) float32, RGB, normalised to [0, 1], letterboxed.
Model output: (1, 21, 8400) — [cx, cy, w, h, class_0..class_16] per anchor.

Target classes (SH17 indices, confirmed from notebook):
  helmet = 10,  vest = 16,  gloves = 9,  mask = 5

Returns per-tracklet dict[str, float]:
  {"helmet": max_conf, "vest": max_conf, "gloves": max_conf, "mask": max_conf}
  0.0 means the item was not detected above conf_threshold.
  None when model is unavailable or crop is too small.

Graceful degradation:
  If the ONNX file is absent or onnxruntime fails, score_crop() returns None
  and PPEDetector disables itself via should_run().
"""

from __future__ import annotations

import logging
import os
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_INPUT_SIZE = 640
_MIN_CROP = 32

# SH17 class indices for the 4 factory-relevant PPE items
_TARGET: dict[str, int] = {"helmet": 10, "vest": 16, "gloves": 9, "mask": 5}


def ppe_preprocess(crop_bgr: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """Letterbox-resize to 640x640 RGB, normalise to [0,1], add batch dim.

    Returns (1, 3, 640, 640) float32 blob.
    """
    h, w = crop_bgr.shape[:2]
    scale = _INPUT_SIZE / max(h, w)
    new_h, new_w = int(h * scale), int(w * scale)
    resized = cv2.resize(crop_bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    canvas = np.full((_INPUT_SIZE, _INPUT_SIZE, 3), 114, dtype=np.uint8)
    pad_y = (_INPUT_SIZE - new_h) // 2
    pad_x = (_INPUT_SIZE - new_w) // 2
    canvas[pad_y : pad_y + new_h, pad_x : pad_x + new_w] = resized

    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return np.transpose(rgb, (2, 0, 1))[np.newaxis]


def ppe_decode(
    raw: np.ndarray[Any, Any],
    conf_threshold: float = 0.25,
    nms_iou_threshold: float = 0.45,
) -> dict[str, float]:
    """Decode YOLOv8 output (1, 21, 8400) → max score per SH17 target class."""
    preds = raw[0].T  # (8400, 21)

    boxes_cxcywh = preds[:, :4]
    class_scores = preds[:, 4:]

    max_scores = class_scores.max(axis=1)
    keep_mask = max_scores >= conf_threshold
    if not np.any(keep_mask):
        return {name: 0.0 for name in _TARGET}

    filtered_boxes = boxes_cxcywh[keep_mask]
    filtered_scores = class_scores[keep_mask]

    cx, cy, bw, bh = (
        filtered_boxes[:, 0],
        filtered_boxes[:, 1],
        filtered_boxes[:, 2],
        filtered_boxes[:, 3],
    )
    x1 = cx - bw / 2
    y1 = cy - bh / 2
    x2 = cx + bw / 2
    y2 = cy + bh / 2

    result: dict[str, float] = {}
    for name, cls_idx in _TARGET.items():
        cls_mask = filtered_scores[:, cls_idx] >= conf_threshold
        if not np.any(cls_mask):
            result[name] = 0.0
            continue

        cls_boxes = np.stack([x1[cls_mask], y1[cls_mask], x2[cls_mask], y2[cls_mask]], axis=1)
        cls_confs = filtered_scores[cls_mask, cls_idx].tolist()

        boxes_xywh = [
            [float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])]
            for b in cls_boxes
        ]
        indices = cv2.dnn.NMSBoxes(boxes_xywh, cls_confs, conf_threshold, nms_iou_threshold)
        if len(indices) == 0:
            result[name] = 0.0
        else:
            flat = indices.flatten() if hasattr(indices, "flatten") else list(indices)
            kept = [cls_confs[int(i)] for i in flat]
            result[name] = float(max(kept))

    return result


class PPEModel:
    """YOLOv8l SH17 ONNX PPE detector.  Stateless — no per-camera state.

    Usage:
        model = PPEModel(get_settings().ppe_model)
        if model.is_available:
            result = model.score_crop(crop_bgr)
            # {"helmet": 0.87, "vest": 0.0, "gloves": 0.63, "mask": 0.0}
    """

    def __init__(self, model_path: str) -> None:
        self._path = model_path
        self._session: Any = None
        self._input_name: str = "images"
        self._conf_threshold: float = 0.25
        self._nms_iou_threshold: float = 0.45
        self._target: dict[str, int] = dict(_TARGET)

        if not model_path:
            _auto = "models/sh17_ppe_yolov8l.onnx"
            if os.path.isfile(_auto):
                model_path = _auto
                self._path = model_path
                logger.info("VMS_PPE_MODEL not set — auto-detected %s", _auto)
            else:
                logger.info(
                    "VMS_PPE_MODEL not set — PPE detection disabled. "
                    "Set VMS_PPE_MODEL=models/sh17_ppe_yolov8l.onnx to enable."
                )
                return

        if not os.path.isfile(model_path):
            logger.warning("ppe_model path %r is not a file — PPE detection disabled.", model_path)
            return

        self._load(model_path)

    def _load(self, path: str) -> None:
        try:
            import onnxruntime as ort  # type: ignore[import-untyped]

            from vms.config import get_settings
            from vms.inference.ort_providers import build_ort_providers

            providers = build_ort_providers()
            sess = ort.InferenceSession(path, providers=providers)
            self._input_name = sess.get_inputs()[0].name
            self._session = sess
            if get_settings().gpu_tensorrt_enabled:
                dummy = np.zeros((1, 3, _INPUT_SIZE, _INPUT_SIZE), dtype=np.float32)
                sess.run(None, {self._input_name: dummy})
                logger.info("PPEModel TRT warm-up complete")
                active = sess.get_providers()
                if active[0] != "TensorrtExecutionProvider":
                    logger.warning(
                        "PPEModel: TRT EP requested but active provider is %s"
                        " -- check ONNX op compatibility",
                        active[0],
                    )
            logger.info("PPEModel loaded from %s", path)
        except Exception as exc:
            logger.warning("PPEModel load failed (%s) — PPE detection disabled.", exc)
            self._session = None

    @property
    def is_available(self) -> bool:
        return self._session is not None

    def score_crop(self, crop_bgr: np.ndarray[Any, Any]) -> dict[str, float] | None:
        """Run PPE detection on a person crop.

        Args:
            crop_bgr: Person bbox crop, (H, W, 3) uint8 BGR.

        Returns:
            Dict with keys "helmet", "vest", "gloves", "mask".
            Each value is the max detection confidence (0.0 = not detected).
            None when model unavailable or crop too small.
        """
        if self._session is None:
            return None

        h, w = crop_bgr.shape[:2]
        if h < _MIN_CROP or w < _MIN_CROP:
            return None

        try:
            tensor = self._preprocess(crop_bgr)
            raw = self._session.run(None, {self._input_name: tensor})
            return self._postprocess(raw[0])
        except Exception as exc:
            logger.debug("PPEModel.score_crop error: %s", exc)
            return None

    def _preprocess(self, crop_bgr: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        return ppe_preprocess(crop_bgr)

    def _postprocess(self, raw: np.ndarray[Any, Any]) -> dict[str, float]:
        return ppe_decode(raw, self._conf_threshold, self._nms_iou_threshold)
