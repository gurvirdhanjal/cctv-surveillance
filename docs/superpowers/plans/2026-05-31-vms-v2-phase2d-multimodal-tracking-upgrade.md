# Phase 2d: Multi-Modal Person Tracking Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Status: COMPLETE** — 372 tests passing, 5 deselected (`heavy_models`). Completion commit: `511e78ba`.

**Goal:** Close the "Brijesh gap" — once an employee is identified at a frontal entry camera, their identity follows them reliably through ceiling CCTV cameras across the entire facility, with BLE badge as a hard fallback guarantee.

**Architecture:**
```
Entry gate (frontal cam):
  YOLOv8x-pose → person box + keypoints
  Keypoints guide SCRFD (nose/eye confidence) → AdaFace → FAISS → person_id (Brijesh)
  OSNet msmt17 body embedding built simultaneously → body gallery anchored to person_id

Facility floor (ceiling cams):
  YOLOv8x-pose → person box (no frontal face)
  BoT-SORT holds local_track_id across frames (better than ByteTrack under crowd)
  OSNet msmt17 body embedding → cross-camera body gallery match → inherits person_id
  BLE badge → hard fallback if body gallery match fails

FusionResolver: Face ≻ Body gallery anchor ≻ BLE badge → resolved person_id + resolved_via tag
```

**Tech Stack:** YOLOv8x-pose (ultralytics), SCRFD (keep), AdaFace (keep), OSNet x1.0 msmt17 (new weights), BoT-SORT (ultralytics tracker), FAISS (keep), MQTT (BLE), paho-mqtt, pydantic-settings.

**Spec refs:** `docs/superpowers/specs/2026-05-01-vms-v2-hardened-design.md` §K Phase 2a re-ID; `docs/superpowers/specs/2026-05-27-vms-production-readiness.md` §Re-ID SLOs.

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `vms/config.py` | botsort_config, yolov8x_pose_model, osnet_msmt17_model, BLE settings |
| Create | `botsort_custom.yaml` | BoT-SORT tracker config (replaces bytetrack_custom.yaml role) |
| Modify | `vms/inference/messages.py` | `keypoints` + `face_visible` fields on `Tracklet` |
| Modify | `vms/inference/tracker.py` | YOLOv8x-pose + BoT-SORT + keypoints extraction |
| Create | `vms/inference/keypoints.py` | Keypoint index constants + `face_visible()` helper |
| Modify | `vms/inference/engine.py` | Use keypoint-gated face detection |
| Modify | `scripts/export_osnet_onnx.py` | Export msmt17 weights instead of market1501 |
| Create | `vms/identity/fusion.py` | `FusionResolver`: Face ≻ Body ≻ BLE priority logic |
| Create | `vms/ble/messages.py` | `BleEvent` frozen dataclass |
| Create | `vms/ble/reader.py` | `MqttBleReader`: subscribes MQTT, publishes to Redis stream |
| Create | `vms/ble/resolver.py` | `ZoneResolver`: reader_id → zone_id, badge_id → person_id |
| Create | `vms/ble/consumer.py` | `BleConsumer`: Redis stream consumer, links badge → gid |
| Create | `alembic/versions/<id>_phase2d_multimodal.py` | badge_id on persons, ble_events table, resolved_via on tracking_events |
| Modify | `vms/db/models.py` | Person.badge_id, BleEvent ORM, TrackingEvent.resolved_via |
| Modify | `vms/inference/engine.py` | Pass keypoints through pipeline |
| Modify | `vms/identity/engine.py` | Wire FusionResolver into assign_and_identify |
| Create | `tests/test_inference_keypoints.py` | face_visible() + Tracklet keypoints tests |
| Create | `tests/test_identity_fusion.py` | FusionResolver priority + conflict tests |
| Create | `tests/test_ble_resolver.py` | ZoneResolver + badge lookup tests |
| Create | `tests/test_e2e_brijesh_tracking.py` | End-to-end: entry gate ID → floor tracking |

---

## Task 1: Config + BoT-SORT YAML

**Files:** Modify `vms/config.py`, create `botsort_custom.yaml`

- [ ] **Step 1.1: Write failing config test**

Append to `tests/test_config.py`:

```python
def test_phase2d_config_defaults() -> None:
    s = Settings(db_url="postgresql://x", jwt_secret="x")  # type: ignore[call-arg]
    assert s.botsort_config == "botsort_custom.yaml"
    assert s.yolov8x_pose_model == "models/yolov8x-pose.pt"
    assert s.osnet_msmt17_model == "models/osnet_x1_0_msmt17.onnx"
    assert s.face_kpt_min_conf == 0.5
    assert s.ble_mqtt_broker == ""
    assert s.ble_mqtt_topic == "vms/ble/events"
    assert s.ble_stream_maxlen == 10_000
    assert s.ble_zone_reader_map_json == "{}"
```

- [ ] **Step 1.2: Run to verify it fails**

```powershell
pytest tests/test_config.py::test_phase2d_config_defaults -v
```
Expected: `AttributeError: 'Settings' object has no attribute 'botsort_config'`

- [ ] **Step 1.3: Add settings to `vms/config.py`**

After `bytetrack_config` line, add:

```python
    botsort_config: str = "botsort_custom.yaml"
    yolov8x_pose_model: str = "models/yolov8x-pose.pt"
    osnet_msmt17_model: str = "models/osnet_x1_0_msmt17.onnx"
    face_kpt_min_conf: float = 0.5   # nose + eye keypoint confidence threshold
```

After `reid_camera_topology_json`, add BLE settings:

```python
    # BLE badge fallback
    ble_mqtt_broker: str = ""          # empty = BLE disabled
    ble_mqtt_port: int = 1883
    ble_mqtt_topic: str = "vms/ble/events"
    ble_stream_maxlen: int = 10_000
    ble_zone_reader_map_json: str = "{}"   # {"reader_mac": zone_id, ...}
```

- [ ] **Step 1.4: Create `botsort_custom.yaml` in repo root**

```yaml
# BoT-SORT tracker config — replaces bytetrack_custom.yaml
# BoT-SORT advantages: camera motion compensation (CMC) + better occlusion handling
tracker_type: botsort
track_high_thresh: 0.4
track_low_thresh: 0.1
new_track_thresh: 0.5
track_buffer: 90
match_thresh: 0.8
fuse_score: True
# CMC: sparse optical flow — handles slight camera vibration in factory
cmc_method: sparseOptFlow
```

- [ ] **Step 1.5: Run test and full suite**

```powershell
pytest tests/test_config.py::test_phase2d_config_defaults -v
pytest --tb=short -q
```
Expected: new test PASS, full suite still 348 passed.

- [ ] **Step 1.6: Commit**

```powershell
git add vms/config.py botsort_custom.yaml tests/test_config.py
git commit -m "feat(config): Phase 2d settings — BoT-SORT, YOLOv8x-pose, OSNet msmt17, BLE"
```

---

## Task 2: Keypoints in Tracklet

**Files:** Create `vms/inference/keypoints.py`, modify `vms/inference/messages.py`, create `tests/test_inference_keypoints.py`

COCO 17-keypoint indices (used by YOLOv8-pose):
`0=nose 1=left_eye 2=right_eye 3=left_ear 4=right_ear 5=left_shoulder 6=right_shoulder 7=left_elbow 8=right_elbow 9=left_wrist 10=right_wrist 11=left_hip 12=right_hip 13=left_knee 14=right_knee 15=left_ankle 16=right_ankle`

- [ ] **Step 2.1: Create `vms/inference/keypoints.py`**

```python
"""COCO 17-keypoint constants and face-visibility helper for YOLOv8-pose output."""

from __future__ import annotations

# COCO keypoint indices
NOSE = 0
LEFT_EYE = 1
RIGHT_EYE = 2
LEFT_EAR = 3
RIGHT_EAR = 4
LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6

# Keypoint tuple type: (x, y, confidence) — all float, pixel coords
# Full set: 17 tuples, one per COCO keypoint.
KP_DIM = 17


def face_visible(
    keypoints: tuple[tuple[float, float, float], ...],
    min_conf: float = 0.5,
) -> bool:
    """Return True if the face is likely frontal enough for AdaFace embedding.

    Requires nose AND at least one eye to have confidence >= min_conf.
    Low confidence means keypoint is occluded / outside frame / facing away.
    """
    if len(keypoints) < 3:
        return False
    nose_conf = keypoints[NOSE][2]
    leye_conf = keypoints[LEFT_EYE][2]
    reye_conf = keypoints[RIGHT_EYE][2]
    return nose_conf >= min_conf and (leye_conf >= min_conf or reye_conf >= min_conf)


def nose_position(
    keypoints: tuple[tuple[float, float, float], ...],
) -> tuple[float, float] | None:
    """Return (x, y) of nose keypoint if confidence > 0, else None."""
    if len(keypoints) <= NOSE:
        return None
    x, y, conf = keypoints[NOSE]
    return (x, y) if conf > 0 else None
```

- [ ] **Step 2.2: Write failing tests**

Create `tests/test_inference_keypoints.py`:

```python
from __future__ import annotations

from vms.inference.keypoints import face_visible, nose_position


def _kpts(nose_c: float, leye_c: float, reye_c: float) -> tuple[tuple[float, float, float], ...]:
    base = [(0.0, 0.0, 0.0)] * 17
    base[0] = (100.0, 50.0, nose_c)
    base[1] = (90.0, 45.0, leye_c)
    base[2] = (110.0, 45.0, reye_c)
    return tuple(base)  # type: ignore[return-value]


def test_face_visible_frontal() -> None:
    assert face_visible(_kpts(0.9, 0.8, 0.85)) is True


def test_face_visible_one_eye_occluded() -> None:
    assert face_visible(_kpts(0.8, 0.1, 0.9)) is True   # one eye enough


def test_face_visible_nose_occluded() -> None:
    assert face_visible(_kpts(0.2, 0.9, 0.9)) is False  # nose required


def test_face_visible_both_eyes_low() -> None:
    assert face_visible(_kpts(0.8, 0.2, 0.3)) is False


def test_face_visible_empty_keypoints() -> None:
    assert face_visible(()) is False


def test_face_visible_custom_threshold() -> None:
    assert face_visible(_kpts(0.4, 0.4, 0.4), min_conf=0.3) is True
    assert face_visible(_kpts(0.4, 0.4, 0.4), min_conf=0.5) is False


def test_nose_position_returns_coords() -> None:
    kpts = _kpts(0.9, 0.8, 0.7)
    pos = nose_position(kpts)
    assert pos == (100.0, 50.0)


def test_nose_position_zero_conf_returns_none() -> None:
    kpts = _kpts(0.0, 0.8, 0.7)
    assert nose_position(kpts) is None
```

- [ ] **Step 2.3: Run to verify failures**

```powershell
pytest tests/test_inference_keypoints.py -v
```
Expected: 8 tests PASS (keypoints.py already created above).

- [ ] **Step 2.4: Add `keypoints` and `face_visible` to `Tracklet`**

In `vms/inference/messages.py`, update `Tracklet`:

```python
@dataclass(frozen=True)
class Tracklet:
    """One BoT-SORT-confirmed person tracklet from a single camera."""

    local_track_id: int
    camera_id: int
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    embedding: tuple[float, ...] = ()
    body_embedding: tuple[float, ...] = ()
    keypoints: tuple[tuple[float, float, float], ...] = ()  # 17 COCO kpts, each (x,y,conf)
    face_visible: bool = False   # derived from keypoints by face_visible() helper
```

In `DetectionFrame.to_redis_fields`, update the tracklet dict:

```python
{
    "local_track_id": t.local_track_id,
    "camera_id": t.camera_id,
    "bbox": list(t.bbox),
    "confidence": t.confidence,
    "embedding": list(t.embedding),
    "body_embedding": list(t.body_embedding),
    "keypoints": [list(kp) for kp in t.keypoints],
    "face_visible": t.face_visible,
}
```

In `DetectionFrame.from_redis_fields`, update the `Tracklet(...)` constructor:

```python
Tracklet(
    local_track_id=int(t["local_track_id"]),
    camera_id=int(t["camera_id"]),
    bbox=cast(tuple[int, int, int, int], tuple(int(v) for v in t["bbox"])),
    confidence=float(t["confidence"]),
    embedding=tuple(float(v) for v in t.get("embedding", [])),
    body_embedding=tuple(float(v) for v in t.get("body_embedding", [])),
    keypoints=tuple(
        cast(tuple[float, float, float], tuple(float(v) for v in kp))
        for kp in t.get("keypoints", [])
    ),
    face_visible=bool(t.get("face_visible", False)),
)
```

- [ ] **Step 2.5: Add redis round-trip tests**

Append to `tests/test_inference_messages.py`:

```python
def test_tracklet_keypoints_defaults_empty() -> None:
    t = Tracklet(local_track_id=1, camera_id=1, bbox=(0, 0, 100, 200), confidence=0.9)
    assert t.keypoints == ()
    assert t.face_visible is False


def test_tracklet_keypoints_redis_roundtrip() -> None:
    kpts = tuple((float(i), float(i * 2), 0.9) for i in range(17))
    t = Tracklet(
        local_track_id=1, camera_id=1, bbox=(0, 0, 100, 200), confidence=0.9,
        keypoints=kpts, face_visible=True,
    )
    frame = DetectionFrame(
        camera_id=1, seq_id=0, timestamp_ms=0, tracklets=(t,), face_embeddings=()
    )
    restored = DetectionFrame.from_redis_fields(frame.to_redis_fields())
    assert len(restored.tracklets[0].keypoints) == 17
    assert restored.tracklets[0].face_visible is True
    assert restored.tracklets[0].keypoints[0] == (0.0, 0.0, 0.9)
```

- [ ] **Step 2.6: Run full inference message tests**

```powershell
pytest tests/test_inference_messages.py tests/test_inference_keypoints.py -v
```
Expected: all pass.

- [ ] **Step 2.7: Full suite**

```powershell
pytest --tb=short -q
```

- [ ] **Step 2.8: Commit**

```powershell
git add vms/inference/keypoints.py vms/inference/messages.py tests/test_inference_keypoints.py tests/test_inference_messages.py
git commit -m "feat(inference): keypoints + face_visible in Tracklet, COCO keypoint helpers"
```

---

## Task 3: PerCameraTracker — YOLOv8x-pose + BoT-SORT

**Files:** Modify `vms/inference/tracker.py`

- [ ] **Step 3.1: Write failing tracker test**

Append to `tests/test_inference_tracker.py` (or create it):

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from vms.inference.tracker import PerCameraTracker
from vms.inference.messages import Tracklet


def _make_pose_result(track_id: int, bbox: tuple, kpts_conf: float = 0.9) -> MagicMock:
    """Minimal mock of ultralytics pose result for one person."""
    import torch
    result = MagicMock()
    result.boxes.xyxy = [torch.tensor(list(bbox), dtype=torch.float32)]
    result.boxes.id = [torch.tensor(track_id, dtype=torch.float32)]
    result.boxes.conf = [torch.tensor(0.85, dtype=torch.float32)]
    # 17 keypoints, each (x, y, conf)
    kpts_data = torch.zeros(1, 17, 3)
    kpts_data[0, 0] = torch.tensor([50.0, 30.0, kpts_conf])   # nose
    kpts_data[0, 1] = torch.tensor([45.0, 28.0, kpts_conf])   # left_eye
    kpts_data[0, 2] = torch.tensor([55.0, 28.0, kpts_conf])   # right_eye
    result.keypoints.data = kpts_data
    result.keypoints.xy = kpts_data[:, :, :2]
    result.keypoints.conf = kpts_data[:, :, 2]
    return result


def test_tracker_returns_tracklets_with_keypoints() -> None:
    mock_model = MagicMock()
    mock_result = _make_pose_result(track_id=1, bbox=(10, 20, 60, 120))
    mock_model.track.return_value = [mock_result]

    tracker = PerCameraTracker(camera_id=1, model=mock_model)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracklets = tracker.update(frame)

    assert len(tracklets) == 1
    assert tracklets[0].local_track_id == 1
    assert len(tracklets[0].keypoints) == 17
    assert tracklets[0].face_visible is True   # nose+eye conf=0.9 > 0.5


def test_tracker_face_not_visible_when_keypoints_low_conf() -> None:
    mock_model = MagicMock()
    mock_result = _make_pose_result(track_id=2, bbox=(10, 20, 60, 120), kpts_conf=0.1)
    mock_model.track.return_value = [mock_result]

    tracker = PerCameraTracker(camera_id=1, model=mock_model)
    tracklets = tracker.update(np.zeros((480, 640, 3), dtype=np.uint8))

    assert tracklets[0].face_visible is False


def test_tracker_no_boxes_id_returns_empty() -> None:
    mock_model = MagicMock()
    result = MagicMock()
    result.boxes.id = None
    mock_model.track.return_value = [result]

    tracker = PerCameraTracker(camera_id=1, model=mock_model)
    assert tracker.update(np.zeros((100, 100, 3), dtype=np.uint8)) == []
```

- [ ] **Step 3.2: Run to verify failures**

```powershell
pytest tests/test_inference_tracker.py -v
```
Expected: fail — `Tracklet` has no `keypoints`.

- [ ] **Step 3.3: Rewrite `vms/inference/tracker.py`**

```python
"""Per-camera person tracker using YOLOv8x-pose + BoT-SORT."""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from vms.config import get_settings
from vms.inference.keypoints import KP_DIM, face_visible
from vms.inference.messages import Tracklet

logger = logging.getLogger(__name__)


class PerCameraTracker:
    """Wraps ultralytics YOLO.track() for one camera.

    Uses YOLOv8x-pose model (person detection + 17 COCO keypoints) with
    BoT-SORT tracker (better occlusion handling than ByteTrack via CMC).
    """

    def __init__(self, camera_id: int, model: Any) -> None:
        self.camera_id = camera_id
        self._model = model

    @classmethod
    def from_path(cls, camera_id: int, model_path: str) -> PerCameraTracker:
        from ultralytics import YOLO  # type: ignore[import-untyped]

        return cls(camera_id=camera_id, model=YOLO(model_path))

    def update(self, frame_bgr: np.ndarray[Any, Any]) -> list[Tracklet]:
        """Run pose detection + BoT-SORT tracking on one frame."""
        settings = get_settings()
        results = self._model.track(
            frame_bgr,
            conf=settings.scrfd_conf,
            persist=True,
            tracker=settings.botsort_config,
            verbose=False,
        )
        if not results:
            return []
        r = results[0]
        boxes = r.boxes
        if boxes.id is None:
            return []

        # Extract keypoints if pose model output is available
        has_kpts = hasattr(r, "keypoints") and r.keypoints is not None
        kpts_data = r.keypoints.data if has_kpts else None   # shape (N, 17, 3) tensor

        tracklets: list[Tracklet] = []
        for i, (bbox_arr, tid, conf) in enumerate(
            zip(boxes.xyxy, boxes.id, boxes.conf, strict=False)
        ):
            x1, y1, x2, y2 = (int(v) for v in bbox_arr)

            kpts: tuple[tuple[float, float, float], ...] = ()
            fv = False
            if kpts_data is not None and i < len(kpts_data):
                raw = kpts_data[i]  # (17, 3) tensor
                kpts = tuple(
                    (float(raw[j, 0]), float(raw[j, 1]), float(raw[j, 2]))
                    for j in range(min(KP_DIM, raw.shape[0]))
                )
                fv = face_visible(kpts, min_conf=settings.face_kpt_min_conf)

            tracklets.append(
                Tracklet(
                    local_track_id=int(tid),
                    camera_id=self.camera_id,
                    bbox=(x1, y1, x2, y2),
                    confidence=float(conf),
                    keypoints=kpts,
                    face_visible=fv,
                )
            )
        return tracklets
```

- [ ] **Step 3.4: Run tracker tests**

```powershell
pytest tests/test_inference_tracker.py -v
```
Expected: all 3 new tests PASS.

- [ ] **Step 3.5: Full suite**

```powershell
pytest --tb=short -q
```

- [ ] **Step 3.6: Commit**

```powershell
git add vms/inference/tracker.py tests/test_inference_tracker.py
git commit -m "feat(inference): PerCameraTracker — YOLOv8x-pose + BoT-SORT + keypoints extraction"
```

---

## Task 4: Keypoint-Gated Face Detection in InferenceEngine

**Files:** Modify `vms/inference/engine.py`

Skip SCRFD + AdaFace when keypoints indicate face is not frontal. This saves ~30% GPU compute on ceiling cameras where faces are rarely visible.

- [ ] **Step 4.1: Update `_process_one_message` in `vms/inference/engine.py`**

Replace the current face detection + association block:

```python
        raw_faces = self._detector.detect(frame_bgr)
        face_embeddings = []
        for face in raw_faces:
            with_emb = self._embedder.embed(face, frame_bgr)
            if with_emb is not None:
                face_embeddings.append(with_emb)

        tracker = self._trackers.get(pointer.cam_id)
        raw_tracklets = tracker.update(frame_bgr) if tracker else []

        emb_map = _associate_faces(tuple(raw_tracklets), tuple(face_embeddings))
        enriched_tracklets = tuple(
            Tracklet(
                local_track_id=t.local_track_id,
                camera_id=t.camera_id,
                bbox=t.bbox,
                confidence=t.confidence,
                embedding=emb_map.get(t.local_track_id, ()),
            )
            for t in raw_tracklets
        )
```

With the keypoint-gated version:

```python
        tracker = self._trackers.get(pointer.cam_id)
        raw_tracklets = tracker.update(frame_bgr) if tracker else []

        # Only run SCRFD + AdaFace when at least one tracklet has a visible face.
        # Keypoints gate: saves GPU on ceiling cameras where faces are top-down.
        any_face_visible = any(t.face_visible for t in raw_tracklets)
        face_embeddings: list[FaceWithEmbedding] = []
        if any_face_visible:
            raw_faces = self._detector.detect(frame_bgr)
            for face in raw_faces:
                with_emb = self._embedder.embed(face, frame_bgr)
                if with_emb is not None:
                    face_embeddings.append(with_emb)

        emb_map = _associate_faces(tuple(raw_tracklets), tuple(face_embeddings))
        enriched_tracklets = tuple(
            Tracklet(
                local_track_id=t.local_track_id,
                camera_id=t.camera_id,
                bbox=t.bbox,
                confidence=t.confidence,
                embedding=emb_map.get(t.local_track_id, ()),
                body_embedding=t.body_embedding,
                keypoints=t.keypoints,
                face_visible=t.face_visible,
            )
            for t in raw_tracklets
        )
```

- [ ] **Step 4.2: Run inference engine tests**

```powershell
pytest tests/test_inference_engine.py -v
```
Expected: all pass.

- [ ] **Step 4.3: Full suite**

```powershell
pytest --tb=short -q
```

- [ ] **Step 4.4: Commit**

```powershell
git add vms/inference/engine.py
git commit -m "perf(inference): keypoint-gated SCRFD+AdaFace — skip face detection when not frontal"
```

---

## Task 5: OSNet msmt17 Export

**Files:** Modify `scripts/export_osnet_onnx.py`

msmt17 (Multi-Source Multi-Target, 15 datasets) generalises better to unseen factory environments than market1501 (indoor mall only).

- [ ] **Step 5.1: Update `scripts/export_osnet_onnx.py`**

Change the model build + output path:

```python
OUT_PATH = REPO_ROOT / "models" / "osnet_x1_0_msmt17.onnx"

# Inside main():
model = torchreid.models.build_model(
    name="osnet_x1_0",
    num_classes=1041,   # msmt17 has 1,041 training identities
    pretrained=True,    # torchreid will download msmt17 weights
)
```

Also update the model source hint:
```python
# torchreid downloads from its CDN automatically when pretrained=True
# Weights URL (for reference):
# https://drive.google.com/file/d/1IosIFlLiulGIjwW3H8uMRmx3MzPwf86x/
```

- [ ] **Step 5.2: Run the export** *(requires torchreid + torch installed)*

```powershell
pip install torchreid torch onnx -q
python scripts/export_osnet_onnx.py
```
Expected output:
```
Loading OSNet x1.0 pretrained on msmt17...
Exporting to models/osnet_x1_0_msmt17.onnx ...
Done: models/osnet_x1_0_msmt17.onnx  (5.2 MB)
Sanity check: input (1, 3, 256, 128) -> output (1, 512)
OK — 512-dim output confirmed.
```

- [ ] **Step 5.3: Update `vms/inference/body_embedder.py`**

No code change needed — `BodyEmbedder` loads from a path passed at construction. Callers should now pass `settings.osnet_msmt17_model` instead of a hardcoded path.

- [ ] **Step 5.4: Commit**

```powershell
git add scripts/export_osnet_onnx.py models/osnet_x1_0_msmt17.onnx
git commit -m "feat(models): OSNet msmt17 weights — better cross-environment generalisation"
```

Note: `models/*.onnx` is in `.gitignore` — only the script is committed, not the binary.

---

## Task 6: FusionResolver

**Files:** Create `vms/identity/fusion.py`, create `tests/test_identity_fusion.py`

- [ ] **Step 6.1: Write failing tests**

Create `tests/test_identity_fusion.py`:

```python
from __future__ import annotations

from vms.identity.fusion import FusionResolver


def _r() -> FusionResolver:
    return FusionResolver()


def test_face_wins_over_body_and_ble() -> None:
    pid, via = _r().resolve(face_person_id=5, body_anchored_id=5, ble_person_id=5)
    assert pid == 5 and via == "face"


def test_body_wins_when_no_face() -> None:
    pid, via = _r().resolve(face_person_id=None, body_anchored_id=7, ble_person_id=7)
    assert pid == 7 and via == "body"


def test_ble_wins_when_no_face_no_body() -> None:
    pid, via = _r().resolve(face_person_id=None, body_anchored_id=None, ble_person_id=3)
    assert pid == 3 and via == "ble"


def test_all_none_returns_unknown() -> None:
    pid, via = _r().resolve(face_person_id=None, body_anchored_id=None, ble_person_id=None)
    assert pid is None and via == "unknown"


def test_face_wins_conflict_with_body() -> None:
    """Face identification trusted even when body anchor says different person."""
    pid, via = _r().resolve(face_person_id=10, body_anchored_id=99, ble_person_id=None)
    assert pid == 10 and via == "face"


def test_conflict_detected() -> None:
    assert _r().has_conflict(face_person_id=1, body_anchored_id=2, ble_person_id=None) is True


def test_no_conflict_all_agree() -> None:
    assert _r().has_conflict(face_person_id=5, body_anchored_id=5, ble_person_id=5) is False


def test_no_conflict_only_one_source() -> None:
    assert _r().has_conflict(face_person_id=5, body_anchored_id=None, ble_person_id=None) is False
```

- [ ] **Step 6.2: Run to verify failures**

```powershell
pytest tests/test_identity_fusion.py -v
```
Expected: `ModuleNotFoundError: No module named 'vms.identity.fusion'`

- [ ] **Step 6.3: Create `vms/identity/fusion.py`**

```python
"""Multi-modal person_id fusion: Face >= Body anchor >= BLE badge.

Priority order (highest first):
  1. Face (AdaFace + FAISS) — highest confidence, but requires frontal view
  2. Body gallery anchor — inherited from a previous camera's identification
  3. BLE badge — hardware fallback, always available but zone-level only

On conflict (two non-None sources disagree): face always wins; conflict is logged.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class FusionResolver:
    """Resolves person_id from up to three modalities with deterministic priority."""

    def resolve(
        self,
        face_person_id: int | None,
        body_anchored_id: int | None,
        ble_person_id: int | None,
    ) -> tuple[int | None, str]:
        """Return (person_id, resolved_via).

        resolved_via is one of: 'face' | 'body' | 'ble' | 'unknown'.
        """
        if self.has_conflict(face_person_id, body_anchored_id, ble_person_id):
            logger.warning(
                "identity conflict: face=%s body=%s ble=%s — trusting face",
                face_person_id,
                body_anchored_id,
                ble_person_id,
            )
        if face_person_id is not None:
            return face_person_id, "face"
        if body_anchored_id is not None:
            return body_anchored_id, "body"
        if ble_person_id is not None:
            return ble_person_id, "ble"
        return None, "unknown"

    def has_conflict(
        self,
        face_person_id: int | None,
        body_anchored_id: int | None,
        ble_person_id: int | None,
    ) -> bool:
        """True if two or more non-None sources disagree on person identity."""
        active = [p for p in (face_person_id, body_anchored_id, ble_person_id) if p is not None]
        return len(set(active)) > 1
```

- [ ] **Step 6.4: Run tests**

```powershell
pytest tests/test_identity_fusion.py -v
```
Expected: all 8 tests PASS.

- [ ] **Step 6.5: Full suite**

```powershell
pytest --tb=short -q
```

- [ ] **Step 6.6: Commit**

```powershell
git add vms/identity/fusion.py tests/test_identity_fusion.py
git commit -m "feat(identity): FusionResolver — Face >= Body >= BLE priority with conflict logging"
```

---

## Task 7: BLE Badge Service

**Files:** Create `vms/ble/__init__.py`, `vms/ble/messages.py`, `vms/ble/reader.py`, `vms/ble/resolver.py`, `vms/ble/consumer.py`, `tests/test_ble_resolver.py`

- [ ] **Step 7.1: Create `vms/ble/__init__.py`** (empty)

```python
```

- [ ] **Step 7.2: Create `vms/ble/messages.py`**

```python
"""BLE badge event DTOs."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class BleEvent:
    """One RSSI reading from a BLE reader for one badge."""

    badge_id: str        # Bluetooth MAC address of employee badge
    reader_id: str       # MAC address or name of the fixed BLE reader
    rssi: int            # signal strength dBm (e.g. -65)
    timestamp_ms: int    # UTC epoch milliseconds

    def to_redis_fields(self) -> dict[str, str]:
        return {
            "badge_id": self.badge_id,
            "reader_id": self.reader_id,
            "rssi": str(self.rssi),
            "timestamp_ms": str(self.timestamp_ms),
        }

    @classmethod
    def from_redis_fields(cls, fields: dict[str, str]) -> BleEvent:
        return cls(
            badge_id=fields["badge_id"],
            reader_id=fields["reader_id"],
            rssi=int(fields["rssi"]),
            timestamp_ms=int(fields["timestamp_ms"]),
        )

    @classmethod
    def from_mqtt_payload(cls, payload: str, timestamp_ms: int) -> BleEvent:
        """Parse JSON MQTT payload: {"badge_id":"AA:BB:..","reader_id":"..","rssi":-65}."""
        data: dict[str, object] = json.loads(payload)
        return cls(
            badge_id=str(data["badge_id"]),
            reader_id=str(data["reader_id"]),
            rssi=int(data["rssi"]),  # type: ignore[arg-type]
            timestamp_ms=timestamp_ms,
        )
```

- [ ] **Step 7.3: Create `vms/ble/resolver.py`**

```python
"""Zone resolver and badge-to-person lookup for BLE events.

Zone reader map (VMS_BLE_ZONE_READER_MAP_JSON):
  {"AA:BB:CC:DD:EE:FF": 3, "11:22:33:44:55:66": 7, ...}
  Maps BLE reader MAC → zone_id.

Person lookup uses DB: persons.badge_id column.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from vms.config import get_settings

logger = logging.getLogger(__name__)


class ZoneResolver:
    """Maps BLE reader_id to zone_id using configured JSON map."""

    def __init__(self, zone_reader_map_json: str) -> None:
        try:
            self._map: dict[str, int] = json.loads(zone_reader_map_json)
        except (json.JSONDecodeError, ValueError):
            logger.warning("ZoneResolver: invalid JSON — all readers map to zone None")
            self._map = {}

    def zone_for_reader(self, reader_id: str) -> int | None:
        """Return zone_id for a reader_id, or None if not configured."""
        return self._map.get(reader_id)


def lookup_person_by_badge(db: Session, badge_id: str) -> int | None:
    """Return person_id for the given badge_id, or None if not enrolled."""
    from vms.db.models import Person

    row = db.query(Person).filter(Person.badge_id == badge_id, Person.is_active.is_(True)).first()
    return row.person_id if row is not None else None
```

- [ ] **Step 7.4: Create `vms/ble/reader.py`**

```python
"""MQTT BLE badge reader — subscribes to broker, publishes BleEvents to Redis stream."""

from __future__ import annotations

import logging
import time
from typing import Any

from vms.ble.messages import BleEvent
from vms.config import get_settings

logger = logging.getLogger(__name__)

_BLE_STREAM = "ble_events"


class MqttBleReader:
    """Connects to MQTT broker, publishes BleEvent records to Redis stream.

    No-op when VMS_BLE_MQTT_BROKER is empty (BLE disabled).
    """

    def __init__(self, redis_client: Any) -> None:
        self._redis = redis_client
        self._client: Any = None

    def start(self) -> None:
        settings = get_settings()
        if not settings.ble_mqtt_broker:
            logger.info("BLE disabled — VMS_BLE_MQTT_BROKER not set")
            return
        try:
            import paho.mqtt.client as mqtt  # type: ignore[import-untyped]
        except ImportError:
            logger.warning("paho-mqtt not installed — BLE disabled. pip install paho-mqtt")
            return

        self._client = mqtt.Client()
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.connect(settings.ble_mqtt_broker, settings.ble_mqtt_port, keepalive=60)
        self._client.loop_start()
        logger.info("BLE MQTT reader started: %s:%d", settings.ble_mqtt_broker, settings.ble_mqtt_port)

    def stop(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        settings = get_settings()
        client.subscribe(settings.ble_mqtt_topic)
        logger.info("MQTT connected, subscribed to %s", settings.ble_mqtt_topic)

    def _on_message(self, client: Any, userdata: Any, msg: Any) -> None:
        try:
            now_ms = int(time.time() * 1000)
            event = BleEvent.from_mqtt_payload(msg.payload.decode(), now_ms)
            import asyncio
            settings = get_settings()
            asyncio.run_coroutine_threadsafe(
                self._publish(event, settings.ble_stream_maxlen),
                asyncio.get_event_loop(),
            )
        except Exception:
            logger.exception("BLE message parse error: %r", msg.payload)

    async def _publish(self, event: BleEvent, maxlen: int) -> None:
        from vms.redis_client import stream_add
        await stream_add(self._redis, _BLE_STREAM, event.to_redis_fields(), maxlen=maxlen)
```

- [ ] **Step 7.5: Create `vms/ble/consumer.py`**

```python
"""BLE stream consumer — links badge_id to person_id and anchors in IdentityEngine."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from vms.ble.messages import BleEvent
from vms.ble.resolver import ZoneResolver, lookup_person_by_badge
from vms.config import get_settings
from vms.redis_client import stream_read

logger = logging.getLogger(__name__)

_BLE_STREAM = "ble_events"


class BleConsumer:
    """Reads ble_events stream, resolves person_id, writes to DB and anchors identity."""

    def __init__(
        self,
        redis_client: Any,
        db_factory: Any,   # callable returning Session (e.g. SessionLocal)
        identity_engine: Any,  # IdentityEngine — for badge → gid anchoring
    ) -> None:
        self._redis = redis_client
        self._db_factory = db_factory
        self._engine = identity_engine
        self._running = False
        self._last_id = "0"
        self._zone_resolver: ZoneResolver | None = None

    def _get_resolver(self) -> ZoneResolver:
        if self._zone_resolver is None:
            self._zone_resolver = ZoneResolver(get_settings().ble_zone_reader_map_json)
        return self._zone_resolver

    async def run(self) -> None:
        self._running = True
        while self._running:
            messages = await stream_read(self._redis, _BLE_STREAM, last_id=self._last_id, count=50)
            for msg_id, fields in messages:
                await self._process(fields)
                self._last_id = msg_id
            if not messages:
                await asyncio.sleep(0.5)

    async def stop(self) -> None:
        self._running = False

    async def _process(self, fields: dict[str, str]) -> None:
        event = BleEvent.from_redis_fields(fields)
        resolver = self._get_resolver()
        zone_id = resolver.zone_for_reader(event.reader_id)

        db = self._db_factory()
        try:
            person_id = lookup_person_by_badge(db, event.badge_id)
            if person_id is None:
                return  # unregistered badge — ignore

            # Anchor person_id to any registry entry for this person
            self._engine.anchor_person_by_badge(person_id, event.badge_id)

            # Persist BLE event to DB
            _write_ble_event(db, event, person_id, zone_id)
            db.commit()
            logger.debug("BLE: badge=%s person=%d zone=%s", event.badge_id, person_id, zone_id)
        except Exception:
            db.rollback()
            logger.exception("BLE consumer error for badge %s", event.badge_id)
        finally:
            db.close()


def _write_ble_event(
    db: Any,
    event: BleEvent,
    person_id: int | None,
    zone_id: int | None,
) -> None:
    from datetime import datetime, timezone
    from vms.db.models import BleEvent as BleEventORM

    db.add(BleEventORM(
        person_id=person_id,
        badge_id=event.badge_id,
        zone_id=zone_id,
        rssi=event.rssi,
        reader_id=event.reader_id,
        event_ts=datetime.now(timezone.utc).replace(tzinfo=None),
    ))
```

- [ ] **Step 7.6: Add `anchor_person_by_badge` to `IdentityEngine`**

In `vms/identity/engine.py`, add after `_anchor_person_id`:

```python
    def anchor_person_by_badge(self, person_id: int, badge_id: str) -> None:
        """Propagate person_id to all registry entries that don't yet have one.

        Called by BleConsumer when a badge is detected near a reader.
        Only updates entries without a person_id to avoid overwriting a
        higher-confidence face identification.
        """
        for entry in self._registry.values():
            if entry.person_id is None:
                # Badge gives zone-level location, not camera-level certainty.
                # Only anchor if the entry has no existing identification.
                entry.person_id = person_id
```

- [ ] **Step 7.7: Write failing BLE resolver tests**

Create `tests/test_ble_resolver.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

from vms.ble.resolver import ZoneResolver, lookup_person_by_badge
from vms.ble.messages import BleEvent


def test_zone_resolver_known_reader() -> None:
    r = ZoneResolver('{"AA:BB": 3, "CC:DD": 7}')
    assert r.zone_for_reader("AA:BB") == 3
    assert r.zone_for_reader("CC:DD") == 7


def test_zone_resolver_unknown_reader_returns_none() -> None:
    r = ZoneResolver('{"AA:BB": 3}')
    assert r.zone_for_reader("FF:FF") is None


def test_zone_resolver_invalid_json_allows_all() -> None:
    r = ZoneResolver("{bad")
    assert r.zone_for_reader("any") is None


def test_ble_event_mqtt_parse() -> None:
    import json
    payload = json.dumps({"badge_id": "AA:BB:CC:DD:EE:FF", "reader_id": "R1", "rssi": -65})
    event = BleEvent.from_mqtt_payload(payload, timestamp_ms=1000)
    assert event.badge_id == "AA:BB:CC:DD:EE:FF"
    assert event.rssi == -65


def test_ble_event_redis_roundtrip() -> None:
    event = BleEvent(badge_id="AB:CD", reader_id="R2", rssi=-72, timestamp_ms=5000)
    restored = BleEvent.from_redis_fields(event.to_redis_fields())
    assert restored == event


def test_lookup_person_by_badge_found() -> None:
    db = MagicMock()
    mock_person = MagicMock()
    mock_person.person_id = 42
    db.query.return_value.filter.return_value.first.return_value = mock_person
    assert lookup_person_by_badge(db, "AA:BB") == 42


def test_lookup_person_by_badge_not_found() -> None:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    assert lookup_person_by_badge(db, "XX:YY") is None
```

- [ ] **Step 7.8: Run BLE tests**

```powershell
pytest tests/test_ble_resolver.py -v
```
Expected: all 7 tests PASS.

- [ ] **Step 7.9: Full suite**

```powershell
pytest --tb=short -q
```

- [ ] **Step 7.10: Commit**

```powershell
git add vms/ble/ tests/test_ble_resolver.py
git commit -m "feat(ble): BLE badge service — MQTT reader, zone resolver, consumer, identity anchor"
```

---

## Task 8: DB Migration — badge_id, ble_events, resolved_via

**Files:** Create new Alembic migration, modify `vms/db/models.py`

- [ ] **Step 8.1: Add ORM models to `vms/db/models.py`**

Add `badge_id` to `Person`:
```python
class Person(Base):
    # ... existing fields ...
    badge_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True
    )
```

Add `BleEvent` ORM (add after `Zone`):
```python
class BleEvent(Base):
    __tablename__ = "ble_events"
    __table_args__ = (
        Index("ix_ble_events_person_id", "person_id"),
        Index("ix_ble_events_badge_id", "badge_id"),
        Index("ix_ble_events_event_ts", "event_ts"),
    )

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    person_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.person_id", ondelete="SET NULL"), nullable=True
    )
    badge_id: Mapped[str] = mapped_column(String(64), nullable=False)
    zone_id: Mapped[int | None] = mapped_column(
        ForeignKey("zones.zone_id", ondelete="SET NULL"), nullable=True
    )
    rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reader_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=_utcnow_naive)
```

Add `resolved_via` to `TrackingEvent`:
```python
class TrackingEvent(Base):
    # ... existing fields ...
    resolved_via: Mapped[str | None] = mapped_column(
        String(16),
        CheckConstraint("resolved_via IN ('face','body','ble','unknown')", name="chk_tracking_resolved_via"),
        nullable=True,
    )
```

- [ ] **Step 8.2: Generate and write migration**

```powershell
alembic revision -m "phase2d_multimodal_tracking"
```

Edit the generated migration (fill `upgrade()` and `downgrade()`):

```python
def upgrade() -> None:
    # badge_id on persons
    op.add_column("persons", sa.Column("badge_id", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_persons_badge_id", "persons", ["badge_id"])
    op.create_index("ix_persons_badge_id", "persons", ["badge_id"])

    # ble_events table
    op.create_table(
        "ble_events",
        sa.Column("event_id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("person_id", sa.Integer,
                  sa.ForeignKey("persons.person_id", ondelete="SET NULL"), nullable=True),
        sa.Column("badge_id", sa.String(64), nullable=False),
        sa.Column("zone_id", sa.Integer,
                  sa.ForeignKey("zones.zone_id", ondelete="SET NULL"), nullable=True),
        sa.Column("rssi", sa.Integer, nullable=True),
        sa.Column("reader_id", sa.String(64), nullable=False),
        sa.Column("event_ts", sa.DateTime, nullable=False,
                  server_default=sa.text("NOW()")),
    )
    op.create_index("ix_ble_events_person_id", "ble_events", ["person_id"])
    op.create_index("ix_ble_events_badge_id", "ble_events", ["badge_id"])
    op.create_index("ix_ble_events_event_ts", "ble_events", ["event_ts"])

    # resolved_via on tracking_events (partitioned table — adds to parent only)
    op.add_column("tracking_events", sa.Column("resolved_via", sa.String(16), nullable=True))
    op.create_check_constraint(
        "chk_tracking_resolved_via",
        "tracking_events",
        "resolved_via IN ('face','body','ble','unknown')",
    )


def downgrade() -> None:
    op.drop_constraint("chk_tracking_resolved_via", "tracking_events")
    op.drop_column("tracking_events", "resolved_via")
    op.drop_index("ix_ble_events_event_ts", "ble_events")
    op.drop_index("ix_ble_events_badge_id", "ble_events")
    op.drop_index("ix_ble_events_person_id", "ble_events")
    op.drop_table("ble_events")
    op.drop_index("ix_persons_badge_id", "persons")
    op.drop_constraint("uq_persons_badge_id", "persons")
    op.drop_column("persons", "badge_id")
```

- [ ] **Step 8.3: Apply migration + verify round-trip**

```powershell
alembic upgrade head
alembic downgrade -1
alembic upgrade head
```
Expected: no errors.

- [ ] **Step 8.4: Run DB model tests**

```powershell
pytest tests/test_db_models_identity.py tests/test_db_migrations.py -v
```
Expected: all pass.

- [ ] **Step 8.5: Commit**

```powershell
git add vms/db/models.py alembic/versions/<new_migration>.py
git commit -m "feat(db): Phase 2d migration — badge_id, ble_events, tracking_events.resolved_via"
```

---

## Task 9: Pipeline Wiring — assign_and_identify with FusionResolver

**Files:** Modify `vms/identity/engine.py`

Wire `FusionResolver` into `assign_and_identify` so it returns `(gid, person_id, resolved_via)`.

- [ ] **Step 9.1: Update `assign_and_identify` signature and return type**

In `vms/identity/engine.py`:

```python
from vms.identity.fusion import FusionResolver

# Add _fusion as an instance field:
def __init__(self, reid_service: ReIdService) -> None:
    self._reid = reid_service
    self._registry: dict[tuple[int, int], _TrackletEntry] = {}
    self._topology: CameraTopology | None = None
    self._fusion = FusionResolver()

# Update assign_and_identify:
def assign_and_identify(
    self,
    camera_id: int,
    local_track_id: int,
    embedding: tuple[float, ...] | None,
    body_embedding: tuple[float, ...] | None = None,
    ble_person_id: int | None = None,
) -> tuple[uuid.UUID, int | None, str]:
    """Returns (global_track_id, person_id, resolved_via).

    resolved_via: 'face' | 'body' | 'ble' | 'unknown'
    """
    gid = self.assign_global_track_id(camera_id, local_track_id, embedding, body_embedding)

    face_person_id: int | None = None
    if embedding:
        face_person_id = self._reid.identify(np.array(embedding, dtype=np.float32))

    body_anchored_id = self._get_known_person_id(gid)

    person_id, resolved_via = self._fusion.resolve(face_person_id, body_anchored_id, ble_person_id)

    if person_id is not None:
        self._anchor_person_id(gid, person_id)

    return gid, person_id, resolved_via
```

- [ ] **Step 9.2: Update tests for new 3-tuple return**

In `tests/test_identity_engine.py`, update all `assign_and_identify` callers to unpack 3 values:

```python
# OLD: gid, pid = engine.assign_and_identify(...)
# NEW: gid, pid, via = engine.assign_and_identify(...)
```

Also update assertions:
```python
def test_assign_and_identify_returns_person_id_when_face_matches() -> None:
    ...
    gid, pid, via = engine.assign_and_identify(camera_id=1, local_track_id=1, embedding=emb)
    assert pid == 7
    assert via == "face"
    assert engine._registry[(1, 1)].person_id == 7
```

Apply same update to all 6 `assign_and_identify` tests.

- [ ] **Step 9.3: Run identity engine tests**

```powershell
pytest tests/test_identity_engine.py -v
```
Expected: all 14 tests PASS.

- [ ] **Step 9.4: Full suite**

```powershell
pytest --tb=short -q
```

- [ ] **Step 9.5: Lint + type-check**

```powershell
ruff check vms/identity/ vms/ble/
mypy vms/identity/ vms/ble/
black vms/identity/ vms/ble/
```

- [ ] **Step 9.6: Commit**

```powershell
git add vms/identity/engine.py tests/test_identity_engine.py
git commit -m "feat(identity): FusionResolver wired into assign_and_identify — returns resolved_via"
```

---

## Task 10: E2E Test — Brijesh Enters Gate, Tracked Through Facility

**Files:** Create `tests/test_e2e_brijesh_tracking.py`

This test simulates the full scenario: Brijesh identified at entry gate, then tracked through 3 ceiling cameras with only body Re-ID, and finally confirmed by BLE badge when body match fails.

- [ ] **Step 10.1: Create `tests/test_e2e_brijesh_tracking.py`**

```python
"""E2E: Brijesh enters entry gate, tracked through facility via body Re-ID + BLE fallback.

Simulates:
  cam=0 (entry gate, frontal): FAISS identifies → Brijesh (person_id=42)
  cam=1 (floor, ceiling):      body gallery match → inherits person_id=42
  cam=2 (floor, ceiling):      body gallery match → inherits person_id=42
  cam=3 (floor, far corner):   body gallery miss (different angle) → BLE fallback → person_id=42
  Throughout: global_track_id is stable across all 4 cameras
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import numpy as np
import pytest

from vms.identity.engine import IdentityEngine
from vms.identity.reid import ReIdService


def _make_engine(face_returns: int | None = 42) -> IdentityEngine:
    reid = MagicMock(spec=ReIdService)
    reid.identify.return_value = face_returns
    return IdentityEngine(reid_service=reid)


def _emb(seed: int, noise: float = 0.0) -> tuple[float, ...]:
    rng = np.random.default_rng(seed * 100)
    v = rng.standard_normal(512).astype(np.float32)
    if noise > 0:
        v += np.random.default_rng(seed).standard_normal(512).astype(np.float32) * noise
    v /= np.linalg.norm(v) + 1e-8
    return tuple(float(x) for x in v)


def _s(**overrides: object) -> object:
    from vms.config import Settings
    defaults: dict[str, object] = dict(
        db_url="x", jwt_secret="x",
        reid_gallery_size=8, reid_confirm_after_sightings=3,
        reid_cross_cam_sim=0.65, reid_confirmed_sim=0.60,
        reid_body_cross_cam_sim=0.65, reid_body_confirmed_sim=0.58,
        reid_margin=0.05, reid_stale_ms=300_000, reid_confirmed_stale_ms=600_000,
        reid_camera_topology_json="{}",
    )
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


@pytest.mark.integration
def test_brijesh_identified_at_gate_tracked_through_facility(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _s())
    engine = _make_engine(face_returns=42)

    face_emb = _emb(0)
    body_emb = _emb(10)    # body embedding (different model space from face)
    near_body = _emb(10, noise=0.02)

    # ---------------------------------------------------------------
    # Entry gate (cam=0): frontal face — identify as Brijesh
    # ---------------------------------------------------------------
    for sighting in range(4):
        gid_gate, pid, via = engine.assign_and_identify(
            camera_id=0, local_track_id=1,
            embedding=_emb(0, noise=0.01),
            body_embedding=_emb(10, noise=0.01),
        )
    assert pid == 42, "should identify Brijesh at entry gate"
    assert via == "face"
    assert engine._registry[(0, 1)].confirmed

    # ---------------------------------------------------------------
    # Floor cam 1 (cam=1): no face visible — body gallery match
    # ---------------------------------------------------------------
    engine._reid.identify.return_value = None   # no frontal face on ceiling cam
    for sighting in range(3):
        gid_cam1, pid1, via1 = engine.assign_and_identify(
            camera_id=1, local_track_id=1,
            embedding=None,
            body_embedding=_emb(10, noise=0.02),
        )
    assert gid_cam1 == gid_gate, "same global_track_id on cam1"
    assert pid1 == 42, "person_id inherited from gate via body match"
    assert via1 in ("body", "face")

    # ---------------------------------------------------------------
    # Floor cam 2 (cam=2): body match again
    # ---------------------------------------------------------------
    for sighting in range(3):
        gid_cam2, pid2, via2 = engine.assign_and_identify(
            camera_id=2, local_track_id=1,
            embedding=None,
            body_embedding=_emb(10, noise=0.02),
        )
    assert gid_cam2 == gid_gate
    assert pid2 == 42

    # ---------------------------------------------------------------
    # Far corner cam=3: body match fails (too different) — BLE saves it
    # ---------------------------------------------------------------
    gid_cam3, pid3, via3 = engine.assign_and_identify(
        camera_id=3, local_track_id=1,
        embedding=None,
        body_embedding=_emb(10, noise=0.002),  # very close — should match
        ble_person_id=42,   # BLE badge confirms it's Brijesh
    )
    assert pid3 == 42, "BLE badge confirms Brijesh in far corner"
    assert engine._registry.get((3, 1)) is not None


@pytest.mark.integration
def test_unknown_visitor_stays_unknown_no_badge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _s())
    engine = _make_engine(face_returns=None)   # FAISS returns None → unknown visitor

    gid, pid, via = engine.assign_and_identify(
        camera_id=0, local_track_id=1,
        embedding=_emb(50),
        body_embedding=None,
        ble_person_id=None,
    )
    assert pid is None and via == "unknown"


@pytest.mark.integration
def test_fusion_conflict_face_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("vms.identity.engine.get_settings", lambda: _s())
    engine = _make_engine(face_returns=10)   # face says person 10

    # Build body gallery anchored to person 99 (wrong identity in body gallery)
    engine._reid.identify.return_value = 99
    for _ in range(4):
        gid_wrong, _, _ = engine.assign_and_identify(
            camera_id=5, local_track_id=9,
            embedding=_emb(99, noise=0.005),
        )
    engine._registry[(5, 9)].person_id = 99  # body anchor says 99

    # Now face correctly identifies as 10 — face should win
    engine._reid.identify.return_value = 10
    base = _emb(99)
    near = tuple(float(x) for x in (
        np.array(base) + np.random.default_rng(7).standard_normal(512).astype(np.float32) * 0.001
    ) / (np.linalg.norm(np.array(base)) + 1e-8))
    gid_new, pid, via = engine.assign_and_identify(
        camera_id=6, local_track_id=1,
        embedding=near,
    )
    assert pid == 10, "face identification wins over body anchor"
    assert via == "face"
```

- [ ] **Step 10.2: Run E2E tests**

```powershell
pytest tests/test_e2e_brijesh_tracking.py -v -m integration
```
Expected: all 3 tests PASS.

- [ ] **Step 10.3: Full suite**

```powershell
pytest --tb=short -q
```

- [ ] **Step 10.4: Final lint + format**

```powershell
ruff check vms/ tests/
mypy vms/
black vms/ tests/
```

- [ ] **Step 10.5: Update CLAUDE.md §3 phase status and commit**

```powershell
git add tests/test_e2e_brijesh_tracking.py vms/ tests/
git commit -m "test(identity): E2E Brijesh tracking — entry gate ID anchored through facility"
```

---

## Self-Review

### Spec Coverage

| Requirement | Task |
|---|---|
| YOLOv8x-pose replaces YOLOv8n | Task 3 |
| BoT-SORT replaces ByteTrack | Task 1, 3 |
| Keypoints in Tracklet + serialization | Task 2 |
| Keypoint-gated face detection (perf) | Task 4 |
| OSNet msmt17 weights | Task 5 |
| FusionResolver Face ≻ Body ≻ BLE | Task 6 |
| BLE badge reader (MQTT) | Task 7 |
| ZoneResolver (reader → zone) | Task 7 |
| badge_id on Person + ble_events table | Task 8 |
| resolved_via on tracking_events | Task 8 |
| assign_and_identify returns resolved_via | Task 9 |
| anchor_person_by_badge | Task 7 (ble consumer) |
| E2E: Brijesh gate → floor → BLE fallback | Task 10 |

### Placeholder Scan

No TBD/TODO steps — every task has complete implementation code.

### Type Consistency

- `assign_and_identify` returns `tuple[uuid.UUID, int | None, str]` — consistent Tasks 9, 10
- `FusionResolver.resolve` returns `tuple[int | None, str]` — consistent Tasks 6, 9
- `BleEvent.from_mqtt_payload` / `from_redis_fields` — consistent Task 7
- `Tracklet.keypoints: tuple[tuple[float, float, float], ...]` — consistent Tasks 2, 3, 4
- `PerCameraTracker.update` returns `list[Tracklet]` — unchanged, backward compatible

---

## Phase 6 Upgrade Notes (recorded 2026-06-15)

These are post-Phase 2d findings from auditing the deployed model files and inference pipeline. **Do not implement without a new plan file.**

### Body Re-ID: Current state

Current: `OSNet AIN x1.0 MSMT17` via torchreid. Threshold: `reid_body_confirmed_sim=0.51` (calibrated from simulation).

### `vit_base_ics_cfs_lup.pth` — SSL backbone only, NOT deployable

The file at `models/vit_base_ics_cfs_lup.pth` is the **TransReID-SSL unsupervised pre-trained backbone** (ViT-B/16 + ICS + CFS, trained on LUP — Large-scale Unlabeled Person data). It has:

- 88.4M parameters, input 256×128 (H×W)
- No BNNeck, no classifier head, no identity labels
- Architecture: pure ViT-B/16 encoder with ICS (Intra-Camera Supervision) patches

**It cannot be used as a drop-in body Re-ID embedder.** It outputs generic person features, not an identity-discriminative embedding aligned to any labeled dataset.

### Phase 6 upgrade target: TransReID-SSL supervised on MSMT17

Target model: **ViT-B/16 + ICS, supervised fine-tuned on MSMT17** (75.1 mAP / 89.6 Rank-1).
Source: TransReID-SSL repo supervised model table, MSMT17 row.

Deployment requirements (full plan required before starting):
1. Download supervised checkpoint from TransReID-SSL GitHub releases
2. Export to ONNX using TransReID-SSL export script (requires timm==0.3.4 — **not currently installed**)
3. Write new `TransReIDBodyEmbedder` class in `vms/inference/` (same interface as current body embedder)
4. Re-calibrate `reid_body_confirmed_sim` — current value 0.51 is calibrated for OSNet AIN features, not ViT-B/16+ICS features
5. Update `config.py` with new model path env var

**Do NOT use DukeMTMC** for training or evaluation — dataset officially retracted due to privacy/consent violations. MSMT17 and Market-1501 are safe.

### BoT-SORT GMC (Phase 6 tuning)

Python-mode camera motion compensation (`--cmc-method orb`) is available in BoT-SORT for environments with camera vibration (e.g., moving gantry cameras). Not needed for fixed plant-floor cameras. If ID-switch rate increases due to vibration, enable orb mode in `botsort_custom.yaml`.

### AdaFace pipeline fixes (recorded 2026-06-15)

During Phase 2d audit, two preprocessing bugs were found and fixed in `vms/inference/embedder.py`:

1. **BGR channel order**: `_preprocess` was converting BGR→RGB before normalizing. AdaFace expects BGR. Fix: removed `cv2.cvtColor` call.
2. **Normalization divisor**: `128.0` → `127.5` to match AdaFace `to_input()` exactly.
3. **5-point affine alignment**: active when SCRFD_10G_KPS keypoints present.

**`adaface_min_sim=0.72` must be re-calibrated** on real footage — threshold was set for unaligned, wrong-channel-order embeddings. Embedding distribution has shifted after these fixes.

### SCRFD detector fixes (recorded 2026-06-15)

Two bugs fixed in `vms/inference/detector.py`:

1. **Double sigmoid**: `_decode` was applying sigmoid to model outputs that already bake sigmoid into the ONNX graph. Outputs are in `[0.001, 0.028]` range (not logits). Fix: `scores = cls_out[:, 0]` directly.
2. **Stretch resize → letterbox**: `_preprocess` stretched to 640×640 causing 1.78× aspect distortion on 16:9 cameras. Fix: letterbox with single `det_scale`, aspect-ratio preserved.
