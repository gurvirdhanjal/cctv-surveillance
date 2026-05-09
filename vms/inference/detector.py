"""SCRFD 2.5g face detector (ONNX).

Input:  (1, 3, 640, 640) float32, normalised (pixel - 127.5) / 128.0, BGR->RGB, CHW
Outputs [cls_s8, cls_s16, cls_s32, bbox_s8, bbox_s16, bbox_s32]:
  cls shapes:  (N, 1)  where N = (640/stride)^2 * 2 anchors
  bbox shapes: (N, 4)  ltrb in stride units from anchor centre
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from vms.config import get_settings
from vms.inference.messages import FaceWithEmbedding

logger = logging.getLogger(__name__)

_INPUT_SIZE = 640
_STRIDES = [8, 16, 32]
_ANCHORS_PER_CELL = 2


class SCRFDDetector:
    """Wraps SCRFD 2.5g ONNX model for face detection."""

    def __init__(
        self,
        session: Any,  # ort.InferenceSession -- stubs are incomplete
        conf_thres: float | None = None,
        nms_thres: float = 0.35,
        min_face_px: int | None = None,
    ) -> None:
        self._sess = session
        self._input_name: str = session.get_inputs()[0].name
        self._conf_thres = (
            conf_thres if conf_thres is not None else get_settings().scrfd_conf
        )
        self._nms_thres = nms_thres
        self._min_face_px = (
            min_face_px if min_face_px is not None else get_settings().min_face_px
        )

    @classmethod
    def from_path(cls, model_path: str) -> SCRFDDetector:
        import onnxruntime as ort  # type: ignore[import-untyped]  # lazy: not available in test env

        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        sess: Any = ort.InferenceSession(model_path, providers=providers)
        return cls(session=sess)

    def detect(
        self, frame_bgr: np.ndarray[Any, np.dtype[Any]]
    ) -> list[FaceWithEmbedding]:
        """Detect faces in a BGR frame. Returns FaceWithEmbedding list (embedding is empty tuple)."""
        h0, w0 = frame_bgr.shape[:2]
        blob = self._preprocess(frame_bgr)
        outputs: list[Any] = self._sess.run(None, {self._input_name: blob})
        return self._decode(outputs, h0, w0)

    def _preprocess(
        self, img: np.ndarray[Any, np.dtype[Any]]
    ) -> np.ndarray[Any, np.dtype[Any]]:
        resized = cv2.resize(img, (_INPUT_SIZE, _INPUT_SIZE))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
        rgb = (rgb - 127.5) / 128.0
        return np.transpose(rgb, (2, 0, 1))[None]

    def _decode(
        self, outputs: list[Any], h0: int, w0: int
    ) -> list[FaceWithEmbedding]:
        cls_outputs = outputs[0:3]
        bbox_outputs = outputs[3:6]

        boxes_all: list[np.ndarray[Any, np.dtype[Any]]] = []
        scores_all: list[np.ndarray[Any, np.dtype[Any]]] = []

        for cls_out, bbox_out, stride in zip(cls_outputs, bbox_outputs, _STRIDES, strict=False):
            n: int = cls_out.shape[0]
            side = _INPUT_SIZE // stride
            hw = side * side
            if n != hw * _ANCHORS_PER_CELL:
                continue

            scores: np.ndarray[Any, np.dtype[Any]] = 1.0 / (1.0 + np.exp(-cls_out[:, 0]))
            keep: np.ndarray[Any, np.dtype[Any]] = scores > self._conf_thres
            if not np.any(keep):
                continue

            scores = scores[keep]
            bbox: np.ndarray[Any, np.dtype[Any]] = bbox_out[keep]

            # grid centers: xs vary along columns, ys along rows (indexing='xy')
            ys, xs = np.meshgrid(np.arange(side), np.arange(side))
            centers = np.stack([xs.ravel(), ys.ravel()], axis=1)
            centers = np.repeat(centers, _ANCHORS_PER_CELL, axis=0)
            centers = centers[keep] * stride

            x1 = centers[:, 0] - bbox[:, 0] * stride
            y1 = centers[:, 1] - bbox[:, 1] * stride
            x2 = centers[:, 0] + bbox[:, 2] * stride
            y2 = centers[:, 1] + bbox[:, 3] * stride

            boxes_all.append(np.stack([x1, y1, x2, y2], axis=1))
            scores_all.append(scores)

        if not boxes_all:
            return []

        boxes: np.ndarray[Any, np.dtype[Any]] = np.concatenate(boxes_all)
        scores_arr: np.ndarray[Any, np.dtype[Any]] = np.concatenate(scores_all)

        boxes[:, [0, 2]] *= w0 / _INPUT_SIZE
        boxes[:, [1, 3]] *= h0 / _INPUT_SIZE

        boxes_xywh = [
            [float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])]
            for b in boxes
        ]
        idxs: Any = cv2.dnn.NMSBoxes(
            boxes_xywh, scores_arr.tolist(), self._conf_thres, self._nms_thres
        )
        if len(idxs) == 0:
            return []

        results: list[FaceWithEmbedding] = []
        for i in idxs.flatten():
            x1i = int(boxes[i, 0])
            y1i = int(boxes[i, 1])
            x2i = int(boxes[i, 2])
            y2i = int(boxes[i, 3])
            if (x2i - x1i) < self._min_face_px or (y2i - y1i) < self._min_face_px:
                continue
            results.append(
                FaceWithEmbedding(
                    bbox=(x1i, y1i, x2i, y2i),
                    confidence=float(scores_arr[i]),
                    embedding=(),
                )
            )
        return results
