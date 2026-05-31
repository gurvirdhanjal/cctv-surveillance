"""Cross-camera re-ID validation script.

Splits a video into two virtual camera streams and runs the full pipeline
(SCRFD face detection -> AdaFace embedding -> IdentityEngine) to validate
that the same person gets the same global_track_id across camera boundaries.

Usage examples:
    # Basic: split a video at midpoint into cam1 / cam2
    python scripts/simulate_cross_camera_reid.py --video path/to/clip.mp4

    # Use webcam live (press Q to quit)
    python scripts/simulate_cross_camera_reid.py --webcam

    # Custom split point and visual overlay
    python scripts/simulate_cross_camera_reid.py --video clip.mp4 --split 0.4 --show

    # Verbose per-frame output + threshold diagnostics
    python scripts/simulate_cross_camera_reid.py --video clip.mp4 --verbose --diag

    # Multi-person crowd test (20-person video)
    python scripts/simulate_cross_camera_reid.py --video crowd.mp4 --split 0.5 --diag

Environment:
    Models must be in models/ directory (downloaded via vms-models download).
    Required: models/scrfd_2.5g.onnx  +  models/adaface_ir50.onnx
    Fallback: InsightFace (pip install insightface) if ONNX models are absent.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), "..")))

# Satisfy pydantic-settings required fields before any VMS import triggers get_settings().
# The script never connects to a DB — these are placeholders only.
os.environ.setdefault("VMS_DB_URL", "postgresql://localhost/vms_simulate_dummy")
os.environ.setdefault("VMS_JWT_SECRET", "simulate-script-not-a-real-secret")

from vms.config import get_settings
from vms.identity.engine import IdentityEngine
from vms.identity.faiss_index import FaissIndex
from vms.identity.reid import ReIdService
from vms.inference.detector import SCRFDDetector
from vms.inference.embedder import AdaFaceEmbedder
from vms.inference.messages import FaceWithEmbedding

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("simulate_reid")


# ---------------------------------------------------------------------------
# Simple IoU-based face tracker (no YOLO needed — face bbox continuity only)
# ---------------------------------------------------------------------------

def _iou(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> float:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


class _FaceTracker:
    """Assigns stable local_track_ids to faces across frames using greedy IoU matching.

    Each camera gets its own tracker instance so IDs don't collide across cameras.
    IOU_THRESHOLD: minimum overlap to consider a face the same person frame-to-frame.
    MAX_MISSING: frames a track can be absent before it is dropped.
    """

    IOU_THRESHOLD = 0.25
    MAX_MISSING = 10

    def __init__(self) -> None:
        self._next_id = 1
        self._active: dict[int, tuple[int, int, int, int]] = {}  # tid -> last_bbox
        self._missing: dict[int, int] = {}  # tid -> frames_since_last_seen

    def update(
        self, faces: list[FaceWithEmbedding]
    ) -> list[tuple[FaceWithEmbedding, int]]:
        """Return list of (face, local_track_id) for each detected face."""
        bboxes = [f.bbox for f in faces]
        assignment: dict[int, int] = {}  # face_idx -> tid
        used_tids: set[int] = set()

        # Match each existing track to nearest detection by IoU
        for tid, last_bbox in list(self._active.items()):
            best_iou, best_idx = 0.0, -1
            for i, bbox in enumerate(bboxes):
                if i in assignment:
                    continue
                iou = _iou(last_bbox, bbox)
                if iou > best_iou:
                    best_iou, best_idx = iou, i
            if best_idx >= 0 and best_iou >= self.IOU_THRESHOLD:
                assignment[best_idx] = tid
                used_tids.add(tid)
                self._missing[tid] = 0
            else:
                self._missing[tid] = self._missing.get(tid, 0) + 1

        # New detections that didn't match → new track
        for i in range(len(bboxes)):
            if i not in assignment:
                assignment[i] = self._next_id
                self._missing[self._next_id] = 0
                self._next_id += 1

        # Update active tracks; drop stale ones
        self._active = {
            assignment[i]: bboxes[i]
            for i in range(len(bboxes))
        }
        for tid in list(self._missing.keys()):
            if self._missing[tid] > self.MAX_MISSING:
                del self._missing[tid]
                self._active.pop(tid, None)

        return [(faces[i], assignment[i]) for i in range(len(faces))]


# ---------------------------------------------------------------------------
# Diagnostics collection
# ---------------------------------------------------------------------------

@dataclass
class _CameraStats:
    camera_id: int
    frames_processed: int = 0
    faces_detected: int = 0
    embeddings_computed: int = 0
    gids_seen: set[uuid.UUID] = field(default_factory=set)
    # gid -> list of raw embedding arrays seen on this camera
    gid_embeddings: dict[uuid.UUID, list[np.ndarray]] = field(  # type: ignore[type-arg]
        default_factory=lambda: defaultdict(list)
    )


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:  # type: ignore[type-arg]
    na = np.linalg.norm(a) + 1e-8
    nb = np.linalg.norm(b) + 1e-8
    return float(np.dot(a / na, b / nb))


def _cross_cam_sims(
    gid: uuid.UUID,
    stats1: _CameraStats,
    stats2: _CameraStats,
) -> list[float]:
    """All pairwise cosine similarities between a gid's embeddings on two cameras."""
    embs1 = stats1.gid_embeddings.get(gid, [])
    embs2 = stats2.gid_embeddings.get(gid, [])
    if not embs1 or not embs2:
        return []
    return [_cosine_sim(e1, e2) for e1 in embs1 for e2 in embs2]


# ---------------------------------------------------------------------------
# Core processing loop
# ---------------------------------------------------------------------------

def process_segment(
    frames: list[np.ndarray],  # type: ignore[type-arg]
    camera_id: int,
    detector: Any,
    embedder: Any,
    engine: IdentityEngine,
    tracker: _FaceTracker,
    stats: _CameraStats,
    verbose: bool,
    show: bool,
    frame_offset: int = 0,
) -> None:
    settings = get_settings()

    for i, frame in enumerate(frames):
        frame_num = frame_offset + i
        raw_faces = detector.detect(frame)
        paired = tracker.update(raw_faces)

        embedded: list[tuple[FaceWithEmbedding, int]] = []
        for face, local_track_id in paired:
            face_with_emb = embedder.embed(face, frame)
            if face_with_emb is not None and face_with_emb.embedding:
                embedded.append((face_with_emb, local_track_id))

        stats.frames_processed += 1
        stats.faces_detected += len(raw_faces)
        stats.embeddings_computed += len(embedded)

        for face_with_emb, local_track_id in embedded:
            gid = engine.assign_global_track_id(
                camera_id=camera_id,
                local_track_id=local_track_id,
                embedding=face_with_emb.embedding,
            )
            stats.gids_seen.add(gid)
            stats.gid_embeddings[gid].append(np.array(face_with_emb.embedding, dtype=np.float32))

            if verbose:
                entry = engine._registry.get((camera_id, local_track_id))
                gallery_len = len(entry.gallery) if entry else 0
                confirmed = entry.confirmed if entry else False
                print(
                    f"  frame={frame_num:5d}  cam={camera_id}  "
                    f"track={local_track_id:3d}  "
                    f"gid={str(gid)[:8]}  "
                    f"gallery={gallery_len}/{settings.reid_gallery_size}  "
                    f"confirmed={'Y' if confirmed else 'N'}  "
                    f"det_conf={face_with_emb.confidence:.2f}"
                )

        if show:
            vis = frame.copy()
            for face, local_track_id in paired:
                x1, y1, x2, y2 = face.bbox
                color = (0, 255, 0) if camera_id == 1 else (255, 165, 0)
                cv2.rectangle(vis, (x1, y1), (x2, y2), color, 2)
                cv2.putText(vis, f"C{camera_id} T{local_track_id}", (x1, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            cv2.putText(vis, f"Camera {camera_id}  Frame {frame_num}", (10, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow("Re-ID Simulation", vis)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_report(
    stats1: _CameraStats,
    stats2: _CameraStats,
    engine: IdentityEngine,
    diag: bool,
) -> None:
    settings = get_settings()
    shared = stats1.gids_seen & stats2.gids_seen
    total = stats1.gids_seen | stats2.gids_seen

    print("\n" + "=" * 60)
    print("CROSS-CAMERA RE-ID SIMULATION REPORT")
    print("=" * 60)

    print(f"\n{'Camera 1':>10}: {stats1.frames_processed} frames  "
          f"{stats1.faces_detected} faces  {stats1.embeddings_computed} embeddings  "
          f"{len(stats1.gids_seen)} unique identities")
    print(f"{'Camera 2':>10}: {stats2.frames_processed} frames  "
          f"{stats2.faces_detected} faces  {stats2.embeddings_computed} embeddings  "
          f"{len(stats2.gids_seen)} unique identities")

    print(f"\n{'Match rate':>15}: {len(shared)}/{len(total)} identities matched "
          f"({100*len(shared)/max(1, len(total)):.0f}%)")

    if shared:
        print(f"{'Matched gids':>15}: " + ", ".join(str(g)[:8] for g in shared))
    cam1_only = stats1.gids_seen - stats2.gids_seen
    cam2_only = stats2.gids_seen - stats1.gids_seen
    if cam1_only:
        print(f"{'Cam1 only':>15}: " + ", ".join(str(g)[:8] for g in cam1_only)
              + "  (person left before cam2)")
    if cam2_only:
        print(f"{'Cam2 only':>15}: " + ", ".join(str(g)[:8] for g in cam2_only)
              + "  (new person on cam2)")

    print(f"\nThresholds in use:")
    print(f"  reid_confirmed_sim    = {settings.reid_confirmed_sim:.2f}  "
          f"(confirmed tracks — lower threshold)")
    print(f"  reid_cross_cam_sim    = {settings.reid_cross_cam_sim:.2f}  "
          f"(new/unconfirmed tracks)")
    print(f"  reid_margin           = {settings.reid_margin:.2f}")
    print(f"  reid_confirm_after    = {settings.reid_confirm_after_sightings} sightings")
    print(f"  reid_gallery_size     = {settings.reid_gallery_size}")
    print(f"  reid_stale_ms         = {settings.reid_stale_ms}ms (unconfirmed)")
    print(f"  reid_confirmed_stale  = {settings.reid_confirmed_stale_ms}ms (confirmed)")

    if diag:
        print("\n--- Similarity Diagnostics ---")
        for gid in sorted(total, key=str):
            on_cam1 = gid in stats1.gids_seen
            on_cam2 = gid in stats2.gids_seen
            tag = "MATCHED" if (on_cam1 and on_cam2) else ("CAM1 ONLY" if on_cam1 else "CAM2 ONLY")
            entry_list = [
                e for (cam, tid), e in engine._registry.items()
                if e.global_track_id == gid
            ]
            confirmed_any = any(e.confirmed for e in entry_list)
            total_gallery = sum(len(e.gallery) for e in entry_list)

            print(f"\n  gid {str(gid)[:8]}  [{tag}]  confirmed={confirmed_any}  "
                  f"total_gallery={total_gallery}")

            if on_cam1 and on_cam2:
                sims = _cross_cam_sims(gid, stats1, stats2)
                if sims:
                    print(f"    cross-cam cosine: min={min(sims):.3f}  "
                          f"avg={sum(sims)/len(sims):.3f}  max={max(sims):.3f}")
                    threshold = (settings.reid_confirmed_sim if confirmed_any
                                 else settings.reid_cross_cam_sim)
                    status = "OK" if max(sims) >= threshold else "BELOW THRESHOLD"
                    print(f"    threshold used: {threshold:.2f}  --> {status}")
                    if max(sims) < threshold:
                        print(f"    RECOMMENDATION: lower reid_confirmed_sim to "
                              f"{max(sims) - 0.02:.2f} or adjust VMS_REID_CONFIRMED_SIM")
            else:
                if not confirmed_any:
                    needed = settings.reid_confirm_after_sightings
                    got = sum(e.sighting_count for e in entry_list)
                    print(f"    not confirmed: {got}/{needed} sightings — "
                          f"increase video segment length or lower VMS_REID_CONFIRM_AFTER_SIGHTINGS")

        print("\n--- Recommendation Summary ---")
        matched_sims = []
        for gid in shared:
            matched_sims.extend(_cross_cam_sims(gid, stats1, stats2))
        if matched_sims:
            print(f"  Observed cross-cam similarities (matched persons): "
                  f"min={min(matched_sims):.3f}  avg={sum(matched_sims)/len(matched_sims):.3f}  "
                  f"max={max(matched_sims):.3f}")
            safe_threshold = min(matched_sims) - 0.05
            print(f"  Safe reid_confirmed_sim for this video: <= {safe_threshold:.2f}")
            print(f"  (current setting: {settings.reid_confirmed_sim:.2f}  "
                  f"{'OK' if settings.reid_confirmed_sim <= safe_threshold else 'TOO HIGH'})")

    print("\n" + "=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-camera re-ID simulation")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", help="Path to video file")
    src.add_argument("--webcam", action="store_true", help="Use webcam (device 0)")
    parser.add_argument("--split", type=float, default=0.5,
                        help="Fraction of frames to assign to camera 1 (default 0.5)")
    parser.add_argument("--show", action="store_true",
                        help="Display video with face overlays")
    parser.add_argument("--verbose", action="store_true",
                        help="Print per-frame detection details")
    parser.add_argument("--diag", action="store_true",
                        help="Print actual cosine similarities and threshold recommendations")
    parser.add_argument("--max-frames", type=int, default=0,
                        help="Limit total frames processed (0 = no limit)")
    args = parser.parse_args()

    settings = get_settings()

    print("Loading models...")
    detector = SCRFDDetector.from_path(settings.scrfd_model)
    embedder = AdaFaceEmbedder.from_path(settings.adaface_model)

    faiss_index = FaissIndex()
    reid_service = ReIdService(faiss_index)
    engine = IdentityEngine(reid_service=reid_service)

    # Read all frames first (for split-point calculation), or stream for webcam
    if args.webcam:
        cap = cv2.VideoCapture(0)
    else:
        cap = cv2.VideoCapture(args.video)

    if not cap.isOpened():
        print(f"ERROR: could not open {'webcam' if args.webcam else args.video}")
        sys.exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames_in_file = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if args.webcam:
        # Webcam: collect first 600 frames (20s at 30fps), then split
        print("Recording from webcam (press Q to stop, or waits for 600 frames)...")
        all_frames: list[np.ndarray] = []  # type: ignore[type-arg]
        while len(all_frames) < 600:
            ret, frame = cap.read()
            if not ret:
                break
            all_frames.append(frame)
            cv2.imshow("Recording (press Q to stop)", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        cv2.destroyAllWindows()
    else:
        print(f"Reading {args.video}  ({total_frames_in_file} frames at {fps:.1f}fps "
              f"= {total_frames_in_file/fps:.1f}s)")
        all_frames = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            all_frames.append(frame)
            if args.max_frames and len(all_frames) >= args.max_frames:
                break
    cap.release()

    if len(all_frames) < 10:
        print("ERROR: fewer than 10 frames — video too short or unreadable.")
        sys.exit(1)

    split_idx = int(len(all_frames) * max(0.1, min(0.9, args.split)))
    cam1_frames = all_frames[:split_idx]
    cam2_frames = all_frames[split_idx:]

    print(f"Split: camera 1 = frames 0–{split_idx-1} ({split_idx/fps:.1f}s)  |  "
          f"camera 2 = frames {split_idx}–{len(all_frames)-1} "
          f"({len(cam2_frames)/fps:.1f}s)")
    print(f"Processing {len(all_frames)} total frames...\n")

    stats1 = _CameraStats(camera_id=1)
    stats2 = _CameraStats(camera_id=2)
    tracker1 = _FaceTracker()
    tracker2 = _FaceTracker()

    t0 = time.time()

    if args.verbose:
        print("--- Camera 1 ---")
    process_segment(cam1_frames, 1, detector, embedder, engine, tracker1,
                    stats1, args.verbose, args.show, frame_offset=0)

    # Evict truly stale entries but keep confirmed ones (they live 10 min)
    engine.evict_stale()

    if args.verbose:
        print("--- Camera 2 ---")
    process_segment(cam2_frames, 2, detector, embedder, engine, tracker2,
                    stats2, args.verbose, args.show, frame_offset=split_idx)

    elapsed = time.time() - t0
    print(f"\nProcessed {len(all_frames)} frames in {elapsed:.1f}s "
          f"({len(all_frames)/elapsed:.0f} fps)")

    if args.show:
        cv2.destroyAllWindows()

    print_report(stats1, stats2, engine, args.diag)


if __name__ == "__main__":
    main()
