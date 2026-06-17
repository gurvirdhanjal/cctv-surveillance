
import cv2
import time
import numpy as np
from collections import deque, Counter
from ultralytics import YOLO
from config import VIDEO_SOURCE, YOLO_MODEL, CONF_THRES
from face_utils import FaceRecognizerONNX
from sklearn.metrics.pairwise import cosine_similarity
import os

# =========================
# PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

face_recognizer = FaceRecognizerONNX(
    scrfd_onnx_path=os.path.join(BASE_DIR, "models", "scrfd_2.5g.onnx"),
    adaface_onnx_path=os.path.join(BASE_DIR, "models", "adaface_ir50.onnx"),
    conf_thres=0.55,
    nms_thres=0.35,
    min_face_size=30
)

employee_db = np.load("employee_db.npy", allow_pickle=True).item()
print("Loaded employees:", list(employee_db.keys()))

employee_db_norm = {
    k: v.astype(np.float32).reshape(1, -1)
    for k, v in employee_db.items()
}

# =========================
# STATE
# =========================
face_scores = {}
global_id_to_employee = {}
employee_to_global = {}          
last_face_check_time = {}

FACE_CHECK_COOLDOWN = 0.7
SCORE_WINDOW = 7
MIN_TRACK_AGE = 1.5

ABSOLUTE_MIN_SCORE = 0.47
LOCK_MEAN_THRES = 0.45
LOCK_PEAK_THRES = 0.60
MARGIN_THRES = 0.08

# =========================
# TRACKING
# =========================
model = YOLO(YOLO_MODEL)

next_global_id = 1
yolo_to_global = {}
active_tracks = {}
lost_tracks = {}

MAX_LOST_TIME = 20
DISAPPEAR_GRACE = 2.0

VOTE_FRAMES = 3
pending_votes = {}

# =========================
# VIDEO
# =========================
def open_video_source(src):
    cap = cv2.VideoCapture(src)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FPS, 25)
    return cap

# =========================
# FACE RECOGNITION
# =========================
def maybe_run_face_recognition(frame, box, global_id, now):
    if global_id in global_id_to_employee:
        return

    if now - last_face_check_time.get(global_id, 0) < FACE_CHECK_COOLDOWN:
        return
    last_face_check_time[global_id] = now

    if global_id not in face_scores:
        face_scores[global_id] = deque(maxlen=SCORE_WINDOW)

    x1, y1, x2, y2 = map(int, box)
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return

    faces = face_recognizer.detect_and_extract(crop)
    if not faces:
        return

    face = max(
        faces,
        key=lambda f: (f["bbox"][2]-f["bbox"][0]) * (f["bbox"][3]-f["bbox"][1])
    )

    fw = face["bbox"][2] - face["bbox"][0]
    fh = face["bbox"][3] - face["bbox"][1]
    if fw < 60 or fh < 60:
        return

    emb = face["embedding"].astype(np.float32).reshape(1, -1)

    scores = []
    for emp, db_emb in employee_db_norm.items():
        s = float(cosine_similarity(emb, db_emb)[0][0])
        scores.append((emp, s))
        print(f"Employee {emp}: cosine similarity = {s:.3f}")

    scores.sort(key=lambda x: x[1], reverse=True)
    best_emp, best_score = scores[0]
    second_score = scores[1][1] if len(scores) > 1 else -1

    if best_score < ABSOLUTE_MIN_SCORE:
        print("[REJECT] Below absolute threshold")
        return

    if best_score - second_score < MARGIN_THRES:
        print("[REJECT] Ambiguous identity (margin)")
        return

    # 🔒 EMPLOYEE OWNERSHIP CHECK
    if best_emp in employee_to_global:
        print(f"[REJECT] {best_emp} already assigned")
        return

    face_scores[global_id].append(best_score)
    mean_score = np.mean(face_scores[global_id])
    peak_score = np.max(face_scores[global_id])

    print(
        f"[SCORE BUFFER] GID {global_id} "
        f"mean={mean_score:.3f} peak={peak_score:.3f}"
    )

    if (
        len(face_scores[global_id]) >= 4 and
        mean_score >= LOCK_MEAN_THRES and
        peak_score >= LOCK_PEAK_THRES
    ):
        global_id_to_employee[global_id] = best_emp
        employee_to_global[best_emp] = global_id
        print(f"[LOCKED] GlobalID {global_id} → {best_emp}")

# =========================
# MAIN LOOP
# =========================
def main():
    global next_global_id
    cap = open_video_source(VIDEO_SOURCE)

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        now = time.time()

        results = model.track(
            frame,
            conf=CONF_THRES,
            persist=True,
            tracker="bytetrack_custom.yaml",
            verbose=False
        )[0]

        if results.boxes.id is not None:
            for box, tid in zip(results.boxes.xyxy, results.boxes.id):
                tid = int(tid)

                if tid not in yolo_to_global:
                    yolo_to_global[tid] = next_global_id
                    active_tracks[next_global_id] = {"first_seen": now}
                    next_global_id += 1

                gid = yolo_to_global[tid]

                if now - active_tracks[gid]["first_seen"] >= MIN_TRACK_AGE:
                    maybe_run_face_recognition(frame, box, gid, now)

                label = global_id_to_employee.get(gid, f"ID {gid}")
                x1, y1, x2, y2 = map(int, box)
                cv2.rectangle(frame, (x1,y1), (x2,y2), (0,255,0), 2)
                cv2.putText(frame, label, (x1, y1-8),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)

        cv2.imshow("CCTV Face Recognition", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
