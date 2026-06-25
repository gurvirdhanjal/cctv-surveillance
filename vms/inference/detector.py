"""SCRFD face detector (ONNX or InsightFace fallback).

Supports both SCRFD variants:
  6-output (no KPS): [cls_s8, cls_s16, cls_s32, bbox_s8, bbox_s16, bbox_s32]
  9-output (KPS):    above + [kps_s8, kps_s16, kps_s32]

Input:  (1, 3, 640, 640) float32, normalised (pixel - 127.5) / 128.0, BGR→RGB, CHW
cls shapes:  (N, 1)   N = (640/stride)^2 x 2 anchors
bbox shapes: (N, 4)   ltrb distances in stride units from anchor centre
kps shapes:  (N, 10)  5 keypoints x 2 (dx, dy) from anchor centre

Default model: scrfd_10g_bnkps.onnx (SCRFD_10G_KPS, WiderFace Hard 82.8%).
Keypoints are 5-point facial landmarks used by AdaFace affine alignment.

Model loading strategy (tried in order):
  1. ONNX file at model_path — fastest, recommended for production.
  2. InsightFace FaceAnalysis — auto-downloads buffalo_l (det_10g.onnx) from CDN.
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


def scrfd_preprocess(
    img: np.ndarray[Any, np.dtype[Any]],
) -> tuple[np.ndarray[Any, np.dtype[Any]], float]:
    """Letterbox-resize to _INPUT_SIZE x _INPUT_SIZE and normalise for SCRFD.

    Returns (blob, det_scale) where det_scale converts model-space coords back to
    original-frame coords via division: original_coord = model_coord / det_scale.
    """
    h0, w0 = img.shape[:2]
    det_scale = min(_INPUT_SIZE / h0, _INPUT_SIZE / w0)
    new_h, new_w = int(h0 * det_scale), int(w0 * det_scale)
    resized = cv2.resize(img, (new_w, new_h))
    canvas = np.zeros((_INPUT_SIZE, _INPUT_SIZE, 3), dtype=np.uint8)
    canvas[:new_h, :new_w] = resized
    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32)
    rgb = (rgb - 127.5) / 128.0
    return np.transpose(rgb, (2, 0, 1))[None], det_scale


def scrfd_decode(
    outputs: list[Any],
    det_scale: float,
    conf_thres: float,
    nms_thres: float,
    min_face_px: int,
) -> list[FaceWithEmbedding]:
    """Decode SCRFD ONNX outputs (6 or 9 tensors) into FaceWithEmbedding list."""
    use_kps = len(outputs) == 9
    cls_outputs = outputs[0:3]
    bbox_outputs = outputs[3:6]
    kps_outputs = outputs[6:9] if use_kps else [None, None, None]

    boxes_all: list[np.ndarray[Any, np.dtype[Any]]] = []
    scores_all: list[np.ndarray[Any, np.dtype[Any]]] = []
    kpss_all: list[np.ndarray[Any, np.dtype[Any]]] = []

    for cls_out, bbox_out, kps_out, stride in zip(
        cls_outputs, bbox_outputs, kps_outputs, _STRIDES, strict=False
    ):
        n: int = cls_out.shape[0]
        side = _INPUT_SIZE // stride
        if n != side * side * _ANCHORS_PER_CELL:
            continue

        scores: np.ndarray[Any, np.dtype[Any]] = cls_out[:, 0]
        keep: np.ndarray[Any, np.dtype[Any]] = scores > conf_thres
        if not np.any(keep):
            continue

        centers: np.ndarray[Any, np.dtype[Any]] = (
            np.stack(np.mgrid[:side, :side][::-1], axis=-1).reshape(-1, 2).astype(np.float32)  # type: ignore[call-overload]
        )
        centers = np.repeat(centers, _ANCHORS_PER_CELL, axis=0) * stride

        centers_k = centers[keep]
        bbox: np.ndarray[Any, np.dtype[Any]] = bbox_out[keep]

        x1 = centers_k[:, 0] - bbox[:, 0] * stride
        y1 = centers_k[:, 1] - bbox[:, 1] * stride
        x2 = centers_k[:, 0] + bbox[:, 2] * stride
        y2 = centers_k[:, 1] + bbox[:, 3] * stride

        boxes_all.append(np.stack([x1, y1, x2, y2], axis=1))
        scores_all.append(scores[keep])

        if use_kps and kps_out is not None:
            kps: np.ndarray[Any, np.dtype[Any]] = kps_out[keep]
            decoded = np.zeros((kps.shape[0], 5, 2), dtype=np.float32)
            for j in range(5):
                decoded[:, j, 0] = centers_k[:, 0] + kps[:, j * 2] * stride
                decoded[:, j, 1] = centers_k[:, 1] + kps[:, j * 2 + 1] * stride
            kpss_all.append(decoded)

    if not boxes_all:
        return []

    boxes: np.ndarray[Any, np.dtype[Any]] = np.concatenate(boxes_all)
    scores_arr: np.ndarray[Any, np.dtype[Any]] = np.concatenate(scores_all)
    kpss_arr: np.ndarray[Any, np.dtype[Any]] | None = (
        np.concatenate(kpss_all) if use_kps and kpss_all else None
    )

    boxes /= det_scale
    if kpss_arr is not None:
        kpss_arr /= det_scale

    boxes_xywh = [[float(b[0]), float(b[1]), float(b[2] - b[0]), float(b[3] - b[1])] for b in boxes]
    idxs: Any = cv2.dnn.NMSBoxes(boxes_xywh, scores_arr.tolist(), conf_thres, nms_thres)
    if len(idxs) == 0:
        return []

    results: list[FaceWithEmbedding] = []
    for i in idxs.flatten():
        x1i = int(boxes[i, 0])
        y1i = int(boxes[i, 1])
        x2i = int(boxes[i, 2])
        y2i = int(boxes[i, 3])
        if (x2i - x1i) < min_face_px or (y2i - y1i) < min_face_px:
            continue
        kps_tuple: tuple[tuple[float, float], ...] = ()
        if kpss_arr is not None:
            kps_tuple = tuple(
                (float(kpss_arr[i, j, 0]), float(kpss_arr[i, j, 1])) for j in range(5)
            )
        results.append(
            FaceWithEmbedding(
                bbox=(x1i, y1i, x2i, y2i),
                confidence=float(scores_arr[i]),
                embedding=(),
                keypoints=kps_tuple,
            )
        )
    return results


def _try_load_insightface(conf_thres: float, min_face_px: int) -> _InsightFaceBackend | None:
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
    def from_path(
        cls, model_path: str
    ) -> SCRFDDetector | _InsightFaceBackend | _YoloFaceBackend | _NullDetector:
        """Load from ONNX file, InsightFace fallback, or null detector (graceful degradation)."""
        settings = get_settings()
        conf = settings.scrfd_conf
        min_px = settings.min_face_px

        if os.path.exists(model_path):
            try:
                import onnxruntime as ort  # type: ignore[import-untyped]  # lazy

                from vms.inference.ort_providers import build_ort_providers

                providers = build_ort_providers()
                sess: Any = ort.InferenceSession(model_path, providers=providers)
                if settings.gpu_tensorrt_enabled:
                    dummy = np.zeros((1, 3, _INPUT_SIZE, _INPUT_SIZE), dtype=np.float32)
                    sess.run(None, {sess.get_inputs()[0].name: dummy})
                    logger.info("SCRFDDetector TRT warm-up complete")
                    active = sess.get_providers()
                    if active[0] != "TensorrtExecutionProvider":
                        logger.warning(
                            "SCRFDDetector: TRT EP requested but active provider is %s"
                            " -- check ONNX op compatibility",
                            active[0],
                        )
                logger.info("SCRFDDetector loaded from %s", model_path)
                return cls(session=sess, conf_thres=conf, min_face_px=min_px)
            except Exception as exc:
                logger.warning("ONNX load failed (%s); trying InsightFace fallback", exc)

        # Fallback 1: legacy face-YOLO (yolov8s-face-lindevs.onnx) — proven in testing
        yolo_face_path = os.path.join(os.path.dirname(model_path), "yolov8s-face-lindevs.onnx")
        if os.path.exists(yolo_face_path):
            try:
                import onnxruntime as ort  # type: ignore

                from vms.inference.ort_providers import build_ort_providers

                providers = build_ort_providers()
                sess = ort.InferenceSession(yolo_face_path, providers=providers)
                logger.info(
                    "SCRFDDetector: %s not found; using legacy yolov8s-face-lindevs.onnx",
                    model_path,
                )
                return _YoloFaceBackend(sess, conf, min_px)
            except Exception as exc:
                logger.warning("yolov8s-face-lindevs.onnx load failed (%s)", exc)

        # Fallback 2: InsightFace auto-download
        backend = _try_load_insightface(conf, min_px)
        if backend is not None:
            return backend

        logger.warning(
            "Face detector unavailable — ONNX file %s not found, legacy yolov8s-face-lindevs.onnx "
            "not found, and InsightFace not installed. "
            "Tracking continues but all persons will be UNKNOWN. "
            "Fix: pip install insightface  OR  place scrfd_2.5g.onnx in models/",
            model_path,
        )
        return _NullDetector()

    def detect(self, frame_bgr: np.ndarray[Any, np.dtype[Any]]) -> list[FaceWithEmbedding]:
        """Detect faces in a BGR frame. Returns FaceWithEmbedding list (embedding is empty tuple)."""
        blob, det_scale = self._preprocess(frame_bgr)
        outputs: list[Any] = self._sess.run(None, {self._input_name: blob})
        return self._decode(outputs, det_scale)

    def _preprocess(
        self, img: np.ndarray[Any, np.dtype[Any]]
    ) -> tuple[np.ndarray[Any, np.dtype[Any]], float]:
        return scrfd_preprocess(img)

    def _decode(self, outputs: list[Any], det_scale: float) -> list[FaceWithEmbedding]:
        return scrfd_decode(
            outputs, det_scale, self._conf_thres, self._nms_thres, self._min_face_px
        )


class _YoloFaceBackend:
    """Legacy yolov8s-face-lindevs.onnx face detector (proven in testing).

    This is the same postprocessing as legacy/main.py and legacy/face_detection.py.
    Used as Tier 2 fallback when scrfd_2.5g.onnx is absent.
    """

    def __init__(self, session: Any, conf_thres: float, min_face_px: int) -> None:
        self._sess = session
        self._input_name: str = session.get_inputs()[0].name
        self._conf_thres = conf_thres
        self._min_face_px = min_face_px

    def detect(self, frame_bgr: np.ndarray[Any, np.dtype[Any]]) -> list[FaceWithEmbedding]:
        h0, w0 = frame_bgr.shape[:2]
        inp, scale, pad_x, pad_y = self._letterbox(frame_bgr)
        outputs = self._sess.run(None, {self._input_name: inp})
        return self._decode(outputs, h0, w0, scale, pad_x, pad_y)

    @staticmethod
    def _letterbox(
        img: np.ndarray[Any, np.dtype[Any]], size: int = 640
    ) -> tuple[np.ndarray[Any, np.dtype[Any]], float, int, int]:
        h, w = img.shape[:2]
        scale = min(size / h, size / w)
        nh, nw = int(h * scale), int(w * scale)
        resized = cv2.resize(img, (nw, nh))
        pad_y, pad_x = (size - nh) // 2, (size - nw) // 2
        padded = cv2.copyMakeBorder(
            resized,
            pad_y,
            size - nh - pad_y,
            pad_x,
            size - nw - pad_x,
            cv2.BORDER_CONSTANT,
            value=(114, 114, 114),
        )
        rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        return np.transpose(rgb, (2, 0, 1))[None], scale, pad_x, pad_y

    def _decode(
        self,
        outputs: list[Any],
        orig_h: int,
        orig_w: int,
        scale: float,
        pad_x: int,
        pad_y: int,
    ) -> list[FaceWithEmbedding]:
        # Handle (1,C,N) or (1,N,C) layout robustly (from legacy _to_nxc)
        raw = outputs[0]
        if raw.ndim == 3 and raw.shape[0] == 1:
            raw = raw[0]
        if raw.ndim == 2 and raw.shape[0] <= 20 and raw.shape[1] > raw.shape[0]:
            raw = raw.T

        raw_boxes: list[tuple[int, int, int, int, float]] = []
        for det in raw:
            if det.shape[0] < 5:
                continue
            obj = float(det[4])
            conf = obj * float(np.max(det[5:])) if det.shape[0] > 5 else obj
            if conf < self._conf_thres:
                continue
            cx, cy, bw, bh = det[:4]
            x1 = int((cx - bw / 2 - pad_x) / scale)
            y1 = int((cy - bh / 2 - pad_y) / scale)
            x2 = int((cx + bw / 2 - pad_x) / scale)
            y2 = int((cy + bh / 2 - pad_y) / scale)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(orig_w - 1, x2), min(orig_h - 1, y2)
            if (x2 - x1) < self._min_face_px or (y2 - y1) < self._min_face_px:
                continue
            raw_boxes.append((x1, y1, x2, y2, conf))

        if not raw_boxes:
            return []

        boxes_xywh = [[x1, y1, x2 - x1, y2 - y1] for x1, y1, x2, y2, _ in raw_boxes]
        scores = [c for *_, c in raw_boxes]
        idxs: Any = cv2.dnn.NMSBoxes(boxes_xywh, scores, self._conf_thres, 0.45)
        if len(idxs) == 0:
            return []
        return [
            FaceWithEmbedding(
                bbox=(raw_boxes[i][0], raw_boxes[i][1], raw_boxes[i][2], raw_boxes[i][3]),
                confidence=raw_boxes[i][4],
                embedding=(),
            )
            for i in idxs.flatten()
        ]


class _NullDetector:
    """No-op detector used when neither ONNX nor InsightFace is available."""

    def detect(self, frame_bgr: np.ndarray[Any, np.dtype[Any]]) -> list[FaceWithEmbedding]:
        return []
