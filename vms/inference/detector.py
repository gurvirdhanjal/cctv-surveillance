"""SCRFD 2.5g face detector (ONNX or InsightFace fallback).

Input:  (1, 3, 640, 640) float32, normalised (pixel - 127.5) / 128.0, BGR->RGB, CHW
Outputs [cls_s8, cls_s16, cls_s32, bbox_s8, bbox_s16, bbox_s32]:
  cls shapes:  (N, 1)  where N = (640/stride)^2 * 2 anchors
  bbox shapes: (N, 4)  ltrb in stride units from anchor centre

Model loading strategy (tried in order):
  1. ONNX file at model_path — fastest, recommended for production.
  2. InsightFace FaceAnalysis — auto-downloads buffalo_l from CDN on first use.
     Install with: pip install insightface onnxruntime
  3. None (graceful degradation) — face detection disabled; tracklets still work
     via YOLO/ByteTrack, but no face embeddings → all persons appear as UNKNOWN.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import cv2
import numpy as np

from vms.config import get_settings
from vms.inference.messages import FaceWithEmbedding

logger = logging.getLogger(__name__)

_INPUT_SIZE = 640
_STRIDES = [8, 16, 32]
_ANCHORS_PER_CELL = 2


def _try_load_insightface(
    conf_thres: float, min_face_px: int
) -> _InsightFaceBackend | None:
    """Try to construct an InsightFace backend. Returns None if not installed."""
    try:
        from insightface.app import FaceAnalysis  # type: ignore[import-not-found]

        logger.info("SCRFD ONNX not found; loading InsightFace buffalo_l (auto-download)")
        app = FaceAnalysis(
            name="buffalo_l",
            allowed_modules=["detection"],
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        app.prepare(ctx_id=0, det_size=(_INPUT_SIZE, _INPUT_SIZE))
        return _InsightFaceBackend(app, conf_thres, min_face_px)
    except Exception as exc:
        logger.warning("InsightFace not available (%s); face detection disabled", exc)
        return None


class _InsightFaceBackend:
    """Thin wrapper so InsightFace presents the same detect() interface as SCRFDDetector."""

    def __init__(self, app: Any, conf_thres: float, min_face_px: int) -> None:
        self._app = app
        self._conf_thres = conf_thres
        self._min_face_px = min_face_px

    def detect(self, frame_bgr: np.ndarray[Any, np.dtype[Any]]) -> list[FaceWithEmbedding]:
        faces = self._app.get(frame_bgr)
        results: list[FaceWithEmbedding] = []
        for f in faces:
            if f.det_score < self._conf_thres:
                continue
            x1, y1, x2, y2 = (int(v) for v in f.bbox)
            if (x2 - x1) < self._min_face_px or (y2 - y1) < self._min_face_px:
                continue
            results.append(
                FaceWithEmbedding(
                    bbox=(x1, y1, x2, y2),
                    confidence=float(f.det_score),
                    embedding=(),
                )
            )
        return results


class SCRFDDetector:
    """Wraps SCRFD 2.5g ONNX model for face detection.

    When model file is absent, falls back to InsightFace auto-download.
    When neither is available, detect() returns [] and logs a warning once.
    """

    def __init__(
        self,
        session: Any,  # ort.InferenceSession -- stubs are incomplete
        conf_thres: float | None = None,
        nms_thres: float = 0.35,
        min_face_px: int | None = None,
    ) -> None:
        self._sess = session
        self._input_name: str = session.get_inputs()[0].name
        self._conf_thres = conf_thres if conf_thres is not None else get_settings().scrfd_conf
        self._nms_thres = nms_thres
        self._min_face_px = min_face_px if min_face_px is not None else get_settings().min_face_px

    @classmethod
    def from_path(cls, model_path: str) -> SCRFDDetector | _InsightFaceBackend | _NullDetector:
        """Load from ONNX file, InsightFace fallback, or null detector (graceful degradation)."""
        settings = get_settings()
        conf = settings.scrfd_conf
        min_px = settings.min_face_px

        if os.path.exists(model_path):
            try:
                import onnxruntime as ort  # type: ignore[import-untyped]  # lazy

                providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                sess: Any = ort.InferenceSession(model_path, providers=providers)
                logger.info("SCRFDDetector loaded from %s", model_path)
                return cls(session=sess, conf_thres=conf, min_face_px=min_px)
            except Exception as exc:
                logger.warning("ONNX load failed (%s); trying InsightFace fallback", exc)

        backend = _try_load_insightface(conf, min_px)
        if backend is not None:
            return backend

        logger.warning(
            "Face detector unavailable — ONNX file %s not found and InsightFace not installed. "
            "Tracking continues but all persons will be UNKNOWN. "
            "Fix: pip install insightface  OR  download %s",
            model_path,
            model_path,
        )
        return _NullDetector()

    def detect(self, frame_bgr: np.ndarray[Any, np.dtype[Any]]) -> list[FaceWithEmbedding]:
        """Detect faces in a BGR frame. Returns FaceWithEmbedding list (embedding is empty tuple)."""
        h0, w0 = frame_bgr.shape[:2]
        blob = self._preprocess(frame_bgr)
        outputs: list[Any] = self._sess.run(None, {self._input_name: blob})
        return self._decode(outputs, h0, w0)

    def _preprocess(self, img: np.ndarray[Any, np.dtype[Any]]) -> np.ndarray[Any, np.dtype[Any]]:
        resized = cv2.resize(img, (_INPUT_SIZE, _INPUT_SIZE))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
        rgb = (rgb - 127.5) / 128.0
        return np.transpose(rgb, (2, 0, 1))[None]

    def _decode(self, outputs: list[Any], h0: int, w0: int) -> list[FaceWithEmbedding]:
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
            [float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])] for b in boxes
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


class _NullDetector:
    """No-op detector used when neither ONNX nor InsightFace is available."""

    def detect(self, frame_bgr: np.ndarray[Any, np.dtype[Any]]) -> list[FaceWithEmbedding]:
        return []
