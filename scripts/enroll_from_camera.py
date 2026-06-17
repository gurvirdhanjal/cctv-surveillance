"""Live face enrollment from a single RTSP camera.

Connects to an RTSP stream, runs SCRFD + AdaFace per frame, and lets you
enroll persons directly into the VMS PostgreSQL database.

Usage:
    # Default: CAM110 Front Gate (reads VMS_CAM_GATE_FRONT_URL from .env)
    venv\\Scripts\\python.exe scripts\\enroll_from_camera.py \\
        --db-url postgresql://vms:vms@localhost:5434/vms_test

    # Explicit URL override:
    venv\\Scripts\\python.exe scripts\\enroll_from_camera.py \\
        --url "rtsp://admin:sss12345@172.16.2.110:554/Streaming/Channels/101" \\
        --db-url postgresql://vms:vms@localhost:5434/vms_test

Controls:
    SPACE   Capture best face from the last 3 s and begin enrollment prompt
    L       List all enrolled persons (printed to terminal)
    Q/ESC   Quit
"""

from __future__ import annotations

import argparse
import logging
import os
import queue
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Torch DLL must be on PATH before any imports that load it transitively.
_torch_lib = _PROJECT_ROOT / "venv" / "Lib" / "site-packages" / "torch" / "lib"
if _torch_lib.is_dir():
    os.environ["PATH"] = str(_torch_lib) + os.pathsep + os.environ.get("PATH", "")

try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

os.environ.setdefault("VMS_JWT_SECRET", "enroll-dummy-secret")
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("enroll").setLevel(logging.INFO)
logger = logging.getLogger("enroll")

import cv2
import numpy as np

# ── constants ────────────────────────────────────────────────────────────────

_DEFAULT_URL = os.environ.get(
    "VMS_CAM_GATE_FRONT_URL",
    "rtsp://admin:sss12345@172.16.2.110:554/Streaming/Channels/101",
)
_DEFAULT_DB = "postgresql://vms:vms@localhost:5434/vms_test"
_ENROLL_CONF = 0.60       # higher than test mode — enrollment should be high-confidence only
_ENROLL_BLUR = 20.0       # min Laplacian variance for face crop to be enrollment-worthy
_ENROLL_MIN_PX = 40       # minimum face dimension in pixels
_CANDIDATE_WINDOW_S = 3.0 # rolling buffer for best-quality candidate


# ── candidate tracking ───────────────────────────────────────────────────────

@dataclass
class _Candidate:
    embedding: tuple[float, ...]
    quality_norm: float  # AdaFace pre-norm L2 (~10-32)
    frame_crop: np.ndarray  # face crop for display confirmation
    timestamp: float


class _CandidateBuffer:
    """Keeps the single best-quality face candidate within a rolling window."""

    def __init__(self, window_s: float = _CANDIDATE_WINDOW_S) -> None:
        self._window_s = window_s
        self._best: _Candidate | None = None
        self._lock = threading.Lock()

    def offer(self, cand: _Candidate) -> None:
        with self._lock:
            now = time.monotonic()
            # Expire old candidate
            if self._best and (now - self._best.timestamp) > self._window_s:
                self._best = None
            # Replace only if better quality
            if self._best is None or cand.quality_norm > self._best.quality_norm:
                self._best = cand

    def take(self) -> _Candidate | None:
        """Return and clear the current best candidate."""
        with self._lock:
            cand = self._best
            self._best = None
            return cand

    def peek_quality(self) -> float:
        with self._lock:
            return self._best.quality_norm if self._best else 0.0


# ── camera reader + inference ────────────────────────────────────────────────

class _CameraWorker:
    """Reads RTSP frames and runs SCRFD+AdaFace in a background thread."""

    def __init__(self, url: str, conf: float, blur: float, min_px: int) -> None:
        self._url = url
        self._conf = conf
        self._blur = blur
        self._min_px = min_px
        self._stop = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._frame_seq = 0
        self._result_q: queue.Queue[tuple[np.ndarray, list[Any]]] = queue.Queue(maxsize=2)
        self.codec_info = "connecting…"
        self.infer_fps: float = 0.0
        self.active_provider: str = "unknown"
        self._detector: Any = None
        self._embedder: Any = None

    def start(self) -> None:
        self._load_models()
        threading.Thread(target=self._read_loop, name="enroll-reader", daemon=True).start()
        threading.Thread(target=self._infer_loop, name="enroll-infer", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def latest_result(self) -> tuple[np.ndarray, list[Any]] | None:
        try:
            return self._result_q.get_nowait()
        except queue.Empty:
            return None

    def _load_models(self) -> None:
        os.environ["VMS_SCRFD_CONF"] = str(self._conf)
        os.environ["VMS_MIN_BLUR"] = str(self._blur)
        os.environ["VMS_MIN_FACE_PX"] = str(self._min_px)
        import onnxruntime as ort
        from vms.inference.detector import SCRFDDetector
        from vms.inference.embedder import AdaFaceEmbedder
        from vms.config import get_settings
        s = get_settings()
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        logger.info("Loading SCRFD from %s", s.scrfd_model)
        scrfd_sess = ort.InferenceSession(s.scrfd_model, providers=providers)
        active = scrfd_sess.get_providers()
        self.active_provider = "CUDA" if "CUDAExecutionProvider" in active else "CPU"
        logger.info("SCRFD running on: %s  (providers: %s)", self.active_provider, active)
        self._detector = SCRFDDetector(scrfd_sess, conf_thres=self._conf, min_face_px=self._min_px)
        logger.info("Loading AdaFace from %s", s.adaface_model)
        ada_sess = ort.InferenceSession(s.adaface_model, providers=providers)
        logger.info("AdaFace running on: %s", ada_sess.get_providers())
        self._embedder = AdaFaceEmbedder(ada_sess, min_face_px=self._min_px, min_blur=self._blur)
        logger.info("Models ready")

    def _open_cap(self) -> "cv2.VideoCapture | None":
        """Open RTSP stream or local webcam. Returns None if unavailable."""
        if self._url.isdigit():
            cap = cv2.VideoCapture(int(self._url))
        else:
            cap = cv2.VideoCapture(self._url, cv2.CAP_FFMPEG)
        if not cap.isOpened():
            cap.release()
            return None
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join(chr((fourcc >> (i * 8)) & 0xFF) for i in range(4)).strip()
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        src = f"webcam:{self._url}" if self._url.isdigit() else "RTSP"
        self.codec_info = f"{src} {codec} {w}x{h} @ {fps:.0f}fps"
        logger.info("Connected: %s", self.codec_info)
        return cap

    def _read_loop(self) -> None:
        cap: Any = None
        fail = 0
        while not self._stop.is_set():
            if cap is None or not cap.isOpened():
                logger.info("Connecting to camera…")
                cap = self._open_cap()
                if cap is None:
                    logger.warning("Could not open stream, retry in 3s")
                    time.sleep(3.0)
                    continue
                fail = 0

            ok, frame = cap.read()
            if not ok:
                fail += 1
                # H.264 decode errors (cabac/qscale) can cause a short burst of bad
                # reads without the stream actually dying — use a higher threshold so
                # we don't trigger an unnecessary 3s reconnect gap on packet loss.
                if fail >= 50:
                    logger.warning("%d consecutive read failures — reconnecting", fail)
                    cap.release()
                    cap = None
                    fail = 0
                time.sleep(0.01)
                continue
            fail = 0
            with self._frame_lock:
                self._latest_frame = frame
                self._frame_seq += 1

    def _infer_loop(self) -> None:
        from vms.inference.messages import FaceWithEmbedding
        last_seq = -1
        _fps_t0 = time.monotonic()
        _fps_count = 0
        # Cap inference at 15fps — no need to process all 50fps for enrollment.
        _min_interval = 1.0 / 15.0
        _last_infer = 0.0
        # SCRFD letterboxes to 640×640 internally; resize input to 640px height first
        # so the CPU preprocessing step (1920×1080→640) is replaced by a much cheaper
        # (640×360→640) pass. AdaFace crops from the same resized frame — 640px height
        # is more than enough for a frontal entry camera at 0.5–3 m range.
        _INFER_H = 640
        while not self._stop.is_set():
            now = time.monotonic()
            if now - _last_infer < _min_interval:
                time.sleep(0.005)
                continue
            with self._frame_lock:
                frame = self._latest_frame
                seq = self._frame_seq
            if frame is None or seq == last_seq:
                time.sleep(0.005)
                continue
            last_seq = seq
            _last_infer = time.monotonic()

            # Downscale to inference height; maintain aspect ratio.
            h0, w0 = frame.shape[:2]
            if h0 > _INFER_H:
                scale = _INFER_H / h0
                infer_frame = cv2.resize(
                    frame,
                    (int(w0 * scale), _INFER_H),
                    interpolation=cv2.INTER_LINEAR,
                )
            else:
                infer_frame = frame
                scale = 1.0

            faces: list[FaceWithEmbedding] = []
            try:
                raw = self._detector.detect(infer_frame)
                for f in raw:
                    if f.confidence < self._conf:
                        continue
                    emb = self._embedder.embed(f, infer_frame)
                    if emb is not None:
                        # Scale bboxes back to original frame coords for display overlay.
                        if scale != 1.0:
                            x1, y1, x2, y2 = f.bbox
                            scaled_bbox = (
                                int(x1 / scale), int(y1 / scale),
                                int(x2 / scale), int(y2 / scale),
                            )
                            from dataclasses import replace as _dc_replace
                            emb = _dc_replace(emb, bbox=scaled_bbox)
                        faces.append(emb)
            except Exception:
                logger.exception("Inference error")
                continue

            # Rolling FPS counter (updated every 2s)
            _fps_count += 1
            elapsed = time.monotonic() - _fps_t0
            if elapsed >= 2.0:
                self.infer_fps = _fps_count / elapsed
                _fps_count = 0
                _fps_t0 = time.monotonic()

            try:
                self._result_q.put_nowait((frame.copy(), faces))
            except queue.Full:
                try:
                    self._result_q.get_nowait()
                    self._result_q.put_nowait((frame.copy(), faces))
                except queue.Empty:
                    pass


# ── database helpers ─────────────────────────────────────────────────────────

def _db_engine(db_url: str) -> Any:
    from sqlalchemy import create_engine
    return create_engine(db_url, pool_pre_ping=True)


def _enroll_person(
    engine: Any,
    name: str,
    employee_id: str,
    embedding: tuple[float, ...],
    quality_norm: float,
) -> int:
    """Insert Person + PersonEmbedding. Returns person_id."""
    from sqlalchemy.orm import Session
    from vms.db.models import Person, PersonEmbedding

    quality_score = min(1.0, max(0.0, quality_norm / 35.0))
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with Session(engine) as db:
        existing = db.query(Person).filter(Person.employee_id == employee_id).first()
        if existing:
            person = existing
            logger.info("Person %s (%s) already exists — adding embedding", name, employee_id)
        else:
            person = Person(employee_id=employee_id, name=name, is_active=True, created_at=now)
            db.add(person)
            db.flush()

        emb_record = PersonEmbedding(
            person_id=person.person_id,
            embedding=list(embedding),
            quality_score=quality_score,
            created_at=now,
        )
        db.add(emb_record)
        db.commit()
        logger.info(
            "Enrolled person_id=%d  employee_id=%s  quality_score=%.3f",
            person.person_id, employee_id, quality_score,
        )
        return int(person.person_id)


def _list_enrolled(engine: Any) -> None:
    from sqlalchemy.orm import Session
    from sqlalchemy import func
    from vms.db.models import Person, PersonEmbedding

    with Session(engine) as db:
        rows = (
            db.query(
                Person.person_id,
                Person.employee_id,
                Person.name,
                func.count(PersonEmbedding.embedding_id).label("n_emb"),
            )
            .outerjoin(PersonEmbedding, Person.person_id == PersonEmbedding.person_id)
            .filter(Person.is_active.is_(True))
            .group_by(Person.person_id)
            .order_by(Person.person_id)
            .all()
        )
    print("\n── Enrolled persons ─────────────────────────────────────────────")
    if not rows:
        print("  (none)")
    else:
        print(f"  {'ID':>4}  {'EmpID':<12}  {'Name':<30}  Embeddings")
        for pid, eid, pname, n in rows:
            print(f"  {pid:>4}  {eid:<12}  {pname:<30}  {n}")
    print("────────────────────────────────────────────────────────────────\n")


# ── prompt helpers (blocking — run in main thread during pause) ──────────────

def _prompt_enrollment(candidate: _Candidate) -> tuple[str, str] | None:
    """Return (name, employee_id) entered by user, or None if cancelled."""
    print("\n── Enrollment ───────────────────────────────────────────────────")
    print(f"  Face quality norm: {candidate.quality_norm:.1f}  (quality_score: {min(1.0, candidate.quality_norm/35.0):.3f})")
    print("  Enter details below. Press ENTER with empty name to cancel.\n")
    name = input("  Person name      : ").strip()
    if not name:
        print("  Cancelled.\n")
        return None
    employee_id = input("  Employee ID      : ").strip()
    if not employee_id:
        # Auto-generate from timestamp so employee_id uniqueness constraint is met
        employee_id = f"EMP-{int(time.time())}"
        print(f"  Auto-assigned ID : {employee_id}")
    print("────────────────────────────────────────────────────────────────\n")
    return name, employee_id


# ── overlay helpers ───────────────────────────────────────────────────────────

_GREEN = (50, 220, 50)
_WHITE = (220, 220, 220)
_YELLOW = (50, 220, 220)
_RED = (50, 50, 220)
_BLACK = (0, 0, 0)
_FONT = cv2.FONT_HERSHEY_SIMPLEX


def _draw_faces(
    frame: np.ndarray,
    faces: list[Any],
    best_quality: float,
    enrolled_count: int,
    codec_info: str,
    infer_fps: float,
    active_provider: str,
    status_msg: str,
) -> None:
    h, w = frame.shape[:2]

    for face in faces:
        x1, y1, x2, y2 = face.bbox
        is_best = abs(face.face_quality_norm - best_quality) < 0.01 and best_quality > 0
        color = _GREEN if is_best else _WHITE
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        label = f"Fq:{face.face_quality_norm:.1f} c:{face.confidence:.2f}"
        cv2.putText(frame, label, (x1, max(y1 - 5, 12)), _FONT, 0.45, _BLACK, 3, cv2.LINE_AA)
        cv2.putText(frame, label, (x1, max(y1 - 5, 12)), _FONT, 0.45, color, 1, cv2.LINE_AA)

    # Header bar (two lines)
    cv2.rectangle(frame, (0, 0), (w, 46), (20, 20, 20), -1)
    header = f"VMS Enroll  {codec_info}  |  Enrolled:{enrolled_count}"
    cv2.putText(frame, header, (6, 16), _FONT, 0.45, _WHITE, 1, cv2.LINE_AA)
    perf = f"Inference: {infer_fps:.1f} fps  [{active_provider}]  |  SPACE=capture  L=list  Q=quit"
    cv2.putText(frame, perf, (6, 38), _FONT, 0.45, _YELLOW, 1, cv2.LINE_AA)

    # Status line
    if status_msg:
        cv2.rectangle(frame, (0, h - 28), (w, h), (20, 20, 20), -1)
        cv2.putText(frame, status_msg, (6, h - 10), _FONT, 0.45, _YELLOW, 1, cv2.LINE_AA)

    # Best candidate indicator
    if best_quality > 0:
        q_label = f"CANDIDATE Fq:{best_quality:.1f}  (SPACE to enroll)"
        cv2.putText(frame, q_label, (6, 64), _FONT, 0.45, _GREEN, 1, cv2.LINE_AA)


# ── main ──────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Enroll persons from a live RTSP camera or webcam.")
    p.add_argument("--url", default=None, help="RTSP URL (default: VMS_CAM_GATE_FRONT_URL from .env)")
    p.add_argument(
        "--webcam",
        action="store_true",
        help="Use local webcam instead of RTSP (device index 0 unless --webcam-index is set)",
    )
    p.add_argument(
        "--webcam-index",
        type=int,
        default=0,
        metavar="INDEX",
        help="Webcam device index (default 0). Only used with --webcam.",
    )
    p.add_argument(
        "--db-url",
        default=os.environ.get("VMS_ENROLL_DB_URL", _DEFAULT_DB),
        help="PostgreSQL URL for enrollment DB (default: %(default)s)",
    )
    p.add_argument("--conf", type=float, default=_ENROLL_CONF, help="SCRFD detection confidence")
    p.add_argument("--blur", type=float, default=_ENROLL_BLUR, help="Minimum Laplacian blur score")
    p.add_argument("--min-px", type=int, default=_ENROLL_MIN_PX, help="Minimum face dimension px")
    return p.parse_args()


def main() -> None:
    args = _parse_args()

    if args.webcam:
        url = str(args.webcam_index)
        stream_label = f"webcam (index {args.webcam_index})"
    else:
        url = args.url if args.url is not None else _DEFAULT_URL
        stream_label = url[:60] + "…" if len(url) > 60 else url

    print(f"\n  VMS Enrollment Script")
    print(f"  Stream  : {stream_label}")
    print(f"  DB      : {args.db_url}")
    print(f"  SCRFD   : conf={args.conf}  blur={args.blur}  min_px={args.min_px}")
    print(f"\n  Loading models (first run may take ~10s)…\n")

    # Initialise DB engine (validates connection early)
    try:
        engine = _db_engine(args.db_url)
        # Quick connectivity check
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("DB connection OK: %s", args.db_url)
    except Exception as exc:
        print(f"\n  ERROR: Cannot connect to database: {exc}")
        print(f"  Try: --db-url postgresql://vms:vms@localhost:5434/vms_test\n")
        sys.exit(1)

    # Start camera + inference
    worker = _CameraWorker(url, args.conf, args.blur, args.min_px)
    worker.start()

    # Count enrolled persons at start
    from sqlalchemy.orm import Session
    from vms.db.models import Person

    def _count_enrolled() -> int:
        with Session(engine) as db:
            return db.query(Person).filter(Person.is_active.is_(True)).count()

    enrolled_count = _count_enrolled()
    buf = _CandidateBuffer()
    status_msg = ""
    status_until = 0.0

    cv2.namedWindow("VMS Enrollment", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("VMS Enrollment", 1280, 720)

    last_frame: np.ndarray | None = None
    last_faces: list[Any] = []

    print("  Window open — walk up to the camera, then press SPACE to enroll.\n")

    # Display frame is updated only when a new inference result arrives (~10fps).
    # We keep a pre-drawn 1280x720 version to avoid re-rendering on every waitKey tick.
    display_cache: np.ndarray | None = None
    _DISP_W, _DISP_H = 1280, 720

    while True:
        result = worker.latest_result()
        if result is not None:
            last_frame, last_faces = result
            # Feed candidates
            for face in last_faces:
                if face.face_quality_norm > 0 and face.embedding:
                    x1, y1, x2, y2 = face.bbox
                    crop = last_frame[y1:y2, x1:x2]
                    buf.offer(_Candidate(
                        embedding=face.embedding,
                        quality_norm=face.face_quality_norm,
                        frame_crop=crop.copy() if crop.size > 0 else np.zeros((1, 1, 3), np.uint8),
                        timestamp=time.monotonic(),
                    ))
            # Build display: draw overlays on full-res then downscale once.
            draw_frame = last_frame.copy()
            now = time.monotonic()
            _draw_faces(
                draw_frame,
                last_faces,
                buf.peek_quality(),
                enrolled_count,
                worker.codec_info,
                worker.infer_fps,
                worker.active_provider,
                status_msg if now < status_until else "",
            )
            display_cache = cv2.resize(draw_frame, (_DISP_W, _DISP_H), interpolation=cv2.INTER_LINEAR)
            cv2.imshow("VMS Enrollment", display_cache)

        key = cv2.waitKey(1) & 0xFF
        if key in (ord("q"), ord("Q"), 27):  # Q or ESC
            break

        elif key == ord(" "):  # SPACE — capture and enroll
            candidate = buf.take()
            if candidate is None:
                status_msg = "No candidate face in buffer — wait for a clear detection"
                status_until = time.monotonic() + 3.0
                continue

            # Show the captured crop
            if candidate.frame_crop.size > 0:
                crop_display = cv2.resize(candidate.frame_crop, (160, 160))
                cv2.imshow("Captured face", crop_display)
                cv2.waitKey(1)

            # Prompt in terminal (blocking — camera keeps reading in background)
            result_prompt = _prompt_enrollment(candidate)
            cv2.destroyWindow("Captured face")

            if result_prompt:
                name, employee_id = result_prompt
                try:
                    pid = _enroll_person(engine, name, employee_id, candidate.embedding, candidate.quality_norm)
                    enrolled_count = _count_enrolled()
                    status_msg = f"Enrolled: {name} ({employee_id})  person_id={pid}"
                    print(f"  OK: {status_msg}\n")
                except Exception as exc:
                    status_msg = f"DB error: {exc}"
                    print(f"  ERROR: {exc}\n")
                status_until = time.monotonic() + 5.0

        elif key in (ord("l"), ord("L")):
            try:
                _list_enrolled(engine)
            except Exception as exc:
                print(f"  DB error listing persons: {exc}")

    worker.stop()
    cv2.destroyAllWindows()
    print("\n  Done.\n")


if __name__ == "__main__":
    main()
