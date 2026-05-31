"""Standalone webcam test for the VMS inference + anomaly pipeline.

Runs DIRECTLY against the webcam — no Redis, no PostgreSQL, no server needed.
Uses the same production code (SCRFDDetector, AdaFaceEmbedder, PerCameraTracker,
ViolenceModel, ViolenceDetector) that the deployed system uses.

Usage:
  python scripts/test_webcam.py                           # webcam index 0
  python scripts/test_webcam.py --camera 1                # webcam index 1
  python scripts/test_webcam.py --rtsp rtsp://...         # RTSP stream
  python scripts/test_webcam.py --no-violence             # skip MoViNet (faster)
  python scripts/test_webcam.py --violence-threshold 0.5  # tune sensitivity

Violence detection is configurable at three levels:
  1. This script flag:  --no-violence        skip entirely for this run
  2. Threshold flag:    --violence-threshold  0.0–1.0, lower = more sensitive
  3. Permanent config:  set VMS_VIOLENCE_MODEL=""  in .env to disable for all processes
                        set VMS_VIOLENCE_THRESHOLD=0.5 to tune permanently

Screen overlay:
  GREEN box  = tracked person with known identity
  RED box    = tracked person with UNKNOWN identity  (triggers UNKNOWN_PERSON alert)
  ORANGE box = tracked person, face not detected / blurry
  Top-left   = violence score bar, FPS, head count
  Top-right  = rolling alert log (last 5)

Controls:
  Q      quit
  E      enrol face — look at camera, press E, type name in terminal
  R      reset enrolled faces (session only)
  SPACE  pause / resume
  V      toggle violence detection on/off mid-session
  +/-    raise/lower violence threshold by 0.05
"""

from __future__ import annotations

# --- Make 'vms' importable when running as a script from any working directory ---
import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# db_url and jwt_secret are required by Settings but unused in this standalone script.
# Set dummy values so pydantic validation passes without a running server.
os.environ.setdefault("VMS_DB_URL", "postgresql://localhost/vms_unused")
os.environ.setdefault("VMS_JWT_SECRET", "webcam-test-dummy-secret")

import argparse
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

import cv2
import numpy as np

# Silence TF/ONNX startup noise
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _draw_box(
    img: np.ndarray,
    x1: int, y1: int, x2: int, y2: int,
    label: str,
    color: tuple[int, int, int],
    thickness: int = 2,
) -> None:
    cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
    # Label background
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.rectangle(img, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
    cv2.putText(img, label, (x1 + 2, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)


def _overlay_hud(
    frame: np.ndarray,
    fps: float,
    head_count: int,
    violence_score: float | None,
    violence_thresh: float,
    alerts: deque[str],
    paused: bool,
) -> None:
    """Draw HUD: top-left stats, top-right alert log."""
    h, w = frame.shape[:2]

    # ---- Top-left stats ----
    lines = [
        f"FPS: {fps:.1f}",
        f"Persons: {head_count}",
    ]
    if violence_score is not None:
        bar_color = (0, 0, 255) if violence_score >= violence_thresh else (0, 200, 0)
        lines.append(f"Violence: {violence_score:.2f} (thr:{violence_thresh:.2f})")
        # Score bar
        bar_w = int(violence_score * 150)
        cv2.rectangle(frame, (10, 80), (160, 95), (60, 60, 60), -1)
        cv2.rectangle(frame, (10, 80), (10 + bar_w, 95), bar_color, -1)
        # Threshold marker
        thr_x = 10 + int(violence_thresh * 150)
        cv2.line(frame, (thr_x, 78), (thr_x, 97), (255, 255, 0), 2)
    if paused:
        lines.insert(0, "PAUSED")

    for i, line in enumerate(lines):
        color = (0, 0, 255) if "PAUSED" in line else (0, 255, 255)
        cv2.putText(frame, line, (10, 25 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3)
        cv2.putText(frame, line, (10, 25 + i * 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 1)

    # ---- Top-right alert log ----
    for j, alert in enumerate(reversed(alerts)):
        y = 25 + j * 20
        cv2.putText(frame, alert, (w - 340, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3)
        cv2.putText(frame, alert, (w - 340, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 100, 255), 1)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="VMS webcam live test")
    parser.add_argument("--camera", type=int, default=0,
                        help="Webcam index (default: 0)")
    parser.add_argument("--rtsp", type=str, default=None,
                        help="RTSP URL (overrides --camera)")
    parser.add_argument("--no-violence", action="store_true",
                        help="Disable MoViNet violence scoring for this run (faster)")
    parser.add_argument("--violence-threshold", type=float, default=None,
                        help="Override violence fire threshold 0.0-1.0 "
                             "(default: VMS_VIOLENCE_THRESHOLD env / config value). "
                             "Lower = more sensitive. Adjustable live with +/- keys.")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    args = parser.parse_args()

    # ---- Load models (all ONNX, no PyTorch required) ----
    # Uses models already in models/:
    #   models/scrfd_2.5g.onnx          — face detector (primary)
    #   models/yolov8s-face-lindevs.onnx — face detector fallback (same as legacy/main.py)
    #   models/adaface_ir50.onnx         — face embedder (recognition)
    # No yolov8n.pt / PyTorch / ultralytics needed for this standalone test.
    print("Loading models...", flush=True)
    from vms.config import get_settings
    settings = get_settings()

    from vms.inference.detector import SCRFDDetector
    from vms.inference.embedder import AdaFaceEmbedder

    detector = SCRFDDetector.from_path(settings.scrfd_model)
    embedder = AdaFaceEmbedder.from_path(settings.adaface_model)
    print(f"  detector: {type(detector).__name__} (ONNX)")
    print(f"  embedder: {type(embedder).__name__} (ONNX)")

    # Violence model (optional)
    violence_model = None
    if not args.no_violence:
        from vms.inference.violence import ViolenceModel
        violence_model = ViolenceModel(settings.violence_model)
        status = "OK" if violence_model.is_available else "disabled (model missing)"
        print(f"  violence: {status}")
    else:
        print("  violence: skipped (--no-violence)")

    # ---- In-session face enrolment ----
    # Maps face embedding → name (session-only; no DB write)
    enrolled: dict[str, np.ndarray] = {}  # name → 512-dim L2-normalised embedding

    def _identify(emb: tuple[float, ...]) -> tuple[str, float]:
        """Cosine similarity match against enrolled faces."""
        if not enrolled or not emb:
            return "UNKNOWN", 0.0
        q = np.array(emb, dtype=np.float32)
        q /= np.linalg.norm(q) + 1e-8
        best_name, best_sim = "UNKNOWN", 0.0
        for name, db_emb in enrolled.items():
            sim = float(np.dot(q, db_emb))
            if sim > best_sim:
                best_sim = sim
                best_name = name
        if best_sim >= settings.adaface_min_sim:
            return best_name, best_sim
        return "UNKNOWN", best_sim

    # ---- Open video source ----
    src: Any = args.rtsp if args.rtsp else args.camera
    print(f"\nOpening video source: {src}")
    cap = cv2.VideoCapture(src)
    if args.rtsp:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    else:
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
        cap.set(cv2.CAP_PROP_FPS, 25)

    if not cap.isOpened():
        print(f"ERROR: cannot open video source {src}", file=sys.stderr)
        sys.exit(1)

    print("Controls: Q=quit  E=enroll face  R=reset enrolled  SPACE=pause")
    print("─" * 60)

    # ---- Minimal IoU tracker (no PyTorch, no ultralytics) ----
    # Mirrors legacy/main.py: each detected face = one tracked person.
    # Stable track IDs are assigned by matching bboxes frame-to-frame via IoU.
    _next_id = [1]
    _tracks: dict[int, dict] = {}  # id → {bbox, last_frame, emb}

    def _iou(a: tuple, b: tuple) -> float:
        ax1, ay1, ax2, ay2 = a
        bx1, by1, bx2, by2 = b
        ix1, iy1 = max(ax1, bx1), max(ay1, by1)
        ix2, iy2 = min(ax2, bx2), min(ay2, by2)
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        if inter == 0:
            return 0.0
        union = (ax2-ax1)*(ay2-ay1) + (bx2-bx1)*(by2-by1) - inter
        return inter / union if union else 0.0

    def _update_tracks(detections: list, fi: int) -> list[dict]:
        """Match detections to existing tracks; return list of active track dicts."""
        used_tracks: set[int] = set()
        result = []
        for det in detections:
            best_id, best_iou = -1, 0.3  # min IoU to consider a match
            for tid, tr in _tracks.items():
                if tid in used_tracks:
                    continue
                iou_val = _iou(det["bbox"], tr["bbox"])
                if iou_val > best_iou:
                    best_iou, best_id = iou_val, tid
            if best_id == -1:
                best_id = _next_id[0]
                _next_id[0] += 1
                _tracks[best_id] = {"bbox": det["bbox"], "last_frame": fi, "emb": ()}
            else:
                _tracks[best_id]["bbox"] = det["bbox"]
                _tracks[best_id]["last_frame"] = fi
            if det.get("emb"):
                _tracks[best_id]["emb"] = det["emb"]
            used_tracks.add(best_id)
            result.append({"id": best_id, **_tracks[best_id]})
        # Evict stale tracks (not seen for 10+ frames)
        stale = [tid for tid, tr in _tracks.items() if fi - tr["last_frame"] > 10]
        for tid in stale:
            del _tracks[tid]
        return result

    # ---- State ----
    alerts: deque[str] = deque(maxlen=5)
    paused = False
    frame_idx = 0
    fps = 0.0
    t_fps = time.time()
    violence_score: float | None = None
    # Allow CLI override; otherwise use config value (VMS_VIOLENCE_THRESHOLD env var)
    violence_thresh = args.violence_threshold if args.violence_threshold is not None \
                      else settings.violence_threshold
    gate_min = settings.violence_gate_min_persons
    violence_enabled = violence_model is not None and not args.no_violence
    print(f"  violence threshold: {violence_thresh:.2f}  (change live with +/- keys, V to toggle)")

    # For enrolment: capture the last detected face embeddings
    last_face_embs: list[tuple[float, ...]] = []

    while True:
        if not paused:
            ok, frame = cap.read()
            if not ok:
                print("Stream ended or lost.")
                break
            frame_idx += 1
        else:
            # Show last frame when paused
            time.sleep(0.05)
            cv2.waitKey(1)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord(" "):
                paused = False
            continue

        display = frame.copy()
        h0, w0 = frame.shape[:2]

        # ---- FPS ----
        if frame_idx % 15 == 0:
            elapsed = time.time() - t_fps
            fps = 15.0 / max(elapsed, 1e-6)
            t_fps = time.time()

        # ---- Face detection + embedding (ONNX only, same as legacy/main.py) ----
        # SCRFDDetector uses scrfd_2.5g.onnx → falls back to yolov8s-face-lindevs.onnx
        faces = detector.detect(frame)
        last_face_embs = []
        detections_for_tracker = []

        for face in faces:
            with_emb = embedder.embed(face, frame)
            emb = with_emb.embedding if with_emb else ()
            if emb:
                last_face_embs.append(emb)
            detections_for_tracker.append({"bbox": face.bbox, "emb": emb})

        # ---- IoU tracking — stable IDs across frames ----
        active_tracks = _update_tracks(detections_for_tracker, frame_idx)
        head_count = len(active_tracks)

        # ---- Violence scoring ----
        if violence_enabled and violence_model and violence_model.is_available \
                and head_count >= gate_min:
            vs = violence_model.score_frame(camera_id=0, frame_bgr=frame)
            if vs is not None:
                violence_score = vs
                if vs >= violence_thresh:
                    msg = f"VIOLENCE {vs:.2f} @ {datetime.now().strftime('%H:%M:%S')}"
                    alerts.append(msg)
                    print(f"  [ALERT] {msg}")

        # ---- Draw tracked faces ----
        for tr in active_tracks:
            x1, y1, x2, y2 = tr["bbox"]
            emb = tr["emb"]

            if emb:
                name, sim = _identify(emb)
                if name == "UNKNOWN":
                    color = (0, 0, 255)   # RED — unknown person
                    label = f"UNKNOWN ({sim:.2f})"
                    alert_msg = f"UNKNOWN @ {datetime.now().strftime('%H:%M:%S')}"
                    if alert_msg not in list(alerts):
                        alerts.append(alert_msg)
                else:
                    color = (0, 200, 0)   # GREEN — recognised
                    label = f"{name} ({sim:.2f})"
            else:
                color = (0, 140, 255)     # ORANGE — face detected, no embedding yet
                label = f"Face #{tr['id']}"

            _draw_box(display, x1, y1, x2, y2, label, color)

        # ---- HUD ----
        _overlay_hud(display, fps, head_count,
                     violence_score if violence_enabled else None,
                     violence_thresh, alerts, paused)

        # ---- Enrolment info bar ----
        enrolled_text = f"Enrolled: {', '.join(enrolled.keys()) or 'none'}"
        cv2.putText(display, enrolled_text, (10, h0 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1)

        cv2.imshow("VMS Live Test  [Q=quit  E=enroll  R=reset  SPACE=pause]", display)
        key = cv2.waitKey(1) & 0xFF

        if key == ord("q"):
            break

        elif key == ord(" "):
            paused = True

        elif key == ord("r"):
            enrolled.clear()
            print("  Enrolled faces cleared.")

        elif key == ord("v"):
            violence_enabled = not violence_enabled
            state = "ON" if violence_enabled else "OFF"
            print(f"  Violence detection toggled {state}")
            if not violence_enabled:
                violence_score = None

        elif key == ord("+") or key == ord("="):
            violence_thresh = min(1.0, round(violence_thresh + 0.05, 2))
            print(f"  Violence threshold raised to {violence_thresh:.2f}")

        elif key == ord("-"):
            violence_thresh = max(0.0, round(violence_thresh - 0.05, 2))
            print(f"  Violence threshold lowered to {violence_thresh:.2f}")

        elif key == ord("e"):
            # Enrol the currently visible face
            if not last_face_embs:
                print("  No face visible — look at the camera and press E again.")
            else:
                # Use the largest / first detected face
                emb_arr = np.array(last_face_embs[0], dtype=np.float32)
                emb_arr /= np.linalg.norm(emb_arr) + 1e-8
                name = input("  Enter name for this face: ").strip()
                if name:
                    enrolled[name] = emb_arr
                    print(f"  Enrolled '{name}'. Enrolled: {list(enrolled.keys())}")
                else:
                    print("  Enrolment cancelled (empty name).")

    cap.release()
    cv2.destroyAllWindows()
    print("Done.")


if __name__ == "__main__":
    main()
