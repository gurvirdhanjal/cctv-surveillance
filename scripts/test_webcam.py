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

    # ---- Load production models ----
    print("Loading models...", flush=True)
    from vms.config import get_settings
    settings = get_settings()

    from vms.inference.detector import SCRFDDetector
    from vms.inference.embedder import AdaFaceEmbedder
    from vms.inference.tracker import PerCameraTracker

    detector = SCRFDDetector.from_path(settings.scrfd_model)
    embedder = AdaFaceEmbedder.from_path(settings.adaface_model)
    tracker  = PerCameraTracker.from_path(camera_id=0, model_path="yolov8n.pt")
    print(f"  detector: {type(detector).__name__}")
    print(f"  embedder: {type(embedder).__name__}")
    print(f"  tracker:  {type(tracker).__name__}")

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

        # ---- Person tracking (YOLO + ByteTrack) ----
        tracklets = tracker.update(frame)
        head_count = len(tracklets)

        # ---- Face detection + embedding ----
        faces = detector.detect(frame)
        last_face_embs = []
        face_emb_map: dict[int, tuple[float, ...]] = {}  # track_id → embedding

        for face in faces:
            fx1, fy1, fx2, fy2 = face.bbox
            fx = (fx1 + fx2) // 2
            fy = (fy1 + fy2) // 2

            with_emb = embedder.embed(face, frame)
            emb = with_emb.embedding if with_emb else ()
            if emb:
                last_face_embs.append(emb)

            # Assign to nearest tracklet
            for t in tracklets:
                x1, y1, x2, y2 = t.bbox
                if x1 <= fx <= x2 and y1 <= fy <= y2:
                    face_emb_map[t.local_track_id] = emb
                    break

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

        # ---- Draw tracklets ----
        for t in tracklets:
            x1, y1, x2, y2 = t.bbox
            emb = face_emb_map.get(t.local_track_id, ())

            if emb:
                name, sim = _identify(emb)
                if name == "UNKNOWN":
                    color = (0, 0, 255)   # RED — UNKNOWN_PERSON
                    label = f"UNKNOWN ({sim:.2f})"
                    alert_msg = f"UNKNOWN @ {datetime.now().strftime('%H:%M:%S')}"
                    if alert_msg not in list(alerts):
                        alerts.append(alert_msg)
                else:
                    color = (0, 200, 0)   # GREEN — known identity
                    label = f"{name} ({sim:.2f})"
            else:
                color = (0, 140, 255)     # ORANGE — no face detected
                label = f"ID:{t.local_track_id}"

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
