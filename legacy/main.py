import cv2
import os
import time
import numpy as np
import onnxruntime as ort

# =========================
# CONFIG
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Video source: use config.py if you have it, else webcam(0)
try:
    from config import VIDEO_SOURCE
except Exception:
    VIDEO_SOURCE = 0

# Model paths
YOLO_ONNX = os.path.join(BASE_DIR, "models", "yolov8s-face-lindevs.onnx")
if not os.path.exists(YOLO_ONNX):
    # common alternative spelling you showed earlier
    alt = os.path.join(BASE_DIR, "models", "yolov8s-face-indevs.onnx")
    if os.path.exists(alt):
        YOLO_ONNX = alt

ADAFACE_ONNX = os.path.join(BASE_DIR, "models", "adaface_ir50.onnx")
DB_PATH = os.path.join(BASE_DIR, "employee_db.npy")

# Detection / recognition thresholds
YOLO_CONF = 0.15
YOLO_NMS_IOU = 0.45

# NOTE: With YOLO crops (no landmarks), scores often drop vs SCRFD.
# Start a bit lower for testing, then tune.
ABSOLUTE_MIN_SCORE = 0.40
MARGIN_THRES = 0.06

MIN_FACE_SIZE = 40          # px (filter tiny detections)
PAD_RATIO = 0.25            # expand bbox for more chin/forehead
MIN_BLUR = 25.0             # lower for CCTV/webcam
RUN_EVERY_N_FRAMES = 1      # set 2/3 if you want faster FPS

# =========================
# LOAD DB
# =========================
if not os.path.exists(DB_PATH):
    raise FileNotFoundError(f"Missing DB: {DB_PATH}")

employee_db = np.load(DB_PATH, allow_pickle=True).item()
names = list(employee_db.keys())
if not names:
    raise RuntimeError("employee_db.npy is empty")

# Normalize DB embeddings and build matrix (N, D)
db_mat = []
for k in names:
    v = employee_db[k].astype(np.float32).reshape(-1)
    v = v / (np.linalg.norm(v) + 1e-9)
    db_mat.append(v)
db_mat = np.vstack(db_mat).astype(np.float32)  # (N, D)

print("[INFO] Loaded employees:", names)

# =========================
# LOAD ONNX MODELS
# =========================
yolo_sess = ort.InferenceSession(YOLO_ONNX, providers=["CPUExecutionProvider"])
face_sess = ort.InferenceSession(ADAFACE_ONNX, providers=["CPUExecutionProvider"])

yolo_input_name = yolo_sess.get_inputs()[0].name
ada_input_name = face_sess.get_inputs()[0].name

print("[INFO] YOLO input:", yolo_input_name)
print("[INFO] AdaFace input:", ada_input_name)

# =========================
# YOLO PREPROCESS (LETTERBOX)
# ========================= 
def letterbox(img, new_shape=640, color=(114, 114, 114)):
    h, w = img.shape[:2]
    scale = min(new_shape / h, new_shape / w)

    nh, nw = int(h * scale), int(w * scale)
    img_resized = cv2.resize(img, (nw, nh))

    pad_y = (new_shape - nh) // 2
    pad_x = (new_shape - nw) // 2

    img_padded = cv2.copyMakeBorder(
        img_resized,
        pad_y,
        new_shape - nh - pad_y,
        pad_x,
        new_shape - nw - pad_x,
        cv2.BORDER_CONSTANT,
        value=color
    )

    return img_padded, scale, pad_x, pad_y

def preprocess_yolo(img):
    img_lb, scale, pad_x, pad_y = letterbox(img, 640)
    img_rgb = cv2.cvtColor(img_lb, cv2.COLOR_BGR2RGB)
    img_norm = img_rgb.astype(np.float32) / 255.0
    img_chw = np.transpose(img_norm, (2, 0, 1))
    return img_chw[None, ...], scale, pad_x, pad_y

# =========================
# YOLO POSTPROCESS (ROBUST)
# =========================
def _to_nxc(output0: np.ndarray) -> np.ndarray:
    """
    Convert YOLO output to (N, C). Supports common layouts:
    - (1, C, N)
    - (1, N, C)
    - (C, N)
    - (N, C)
    """
    x = output0
    if x.ndim == 3 and x.shape[0] == 1:
        x = x[0]
    if x.ndim != 2:
        raise ValueError(f"Unexpected YOLO output shape: {output0.shape}")

    # If first dim looks like channels (<= 20) assume (C, N) and transpose
    if x.shape[0] <= 20 and x.shape[1] > x.shape[0]:
        x = x.T
    return x  # (N, C)

def postprocess_yolo(yolo_out, orig_h, orig_w, scale, pad_x, pad_y, conf_thres=0.15):
    raw_boxes = []
    output0 = yolo_out[0]
    preds = _to_nxc(output0)  # (N, C)

    for det in preds:
        if det.shape[0] < 5:
            continue

        # Handle conf format:
        # - if only 5 values: (cx,cy,w,h,conf)
        # - if more: conf = obj * max(cls_probs)
        obj = float(det[4])
        if det.shape[0] > 5:
            cls_conf = float(np.max(det[5:])) if det.shape[0] > 6 else float(det[5])
            conf = obj * cls_conf
        else:
            conf = obj

        if conf < conf_thres:
            continue

        cx, cy, bw, bh = det[:4]

        # coords are in 640-space pixels (because of letterbox)
        x1 = cx - bw / 2 - pad_x
        y1 = cy - bh / 2 - pad_y
        x2 = cx + bw / 2 - pad_x
        y2 = cy + bh / 2 - pad_y

        # undo scale
        x1 /= scale
        y1 /= scale
        x2 /= scale
        y2 /= scale

        x1, y1, x2, y2 = map(int, [x1, y1, x2, y2])

        # clamp
        x1 = max(0, min(orig_w - 1, x1))
        y1 = max(0, min(orig_h - 1, y1))
        x2 = max(0, min(orig_w - 1, x2))
        y2 = max(0, min(orig_h - 1, y2))

        if (x2 - x1) < MIN_FACE_SIZE or (y2 - y1) < MIN_FACE_SIZE:
            continue

        raw_boxes.append((x1, y1, x2, y2, conf))

    return raw_boxes

# =========================
# NMS
# =========================
def apply_nms(raw_boxes, iou_thresh=0.45):
    if len(raw_boxes) == 0:
        return []

    boxes_xywh = []
    scores = []
    for (x1, y1, x2, y2, conf) in raw_boxes:
        boxes_xywh.append([x1, y1, x2 - x1, y2 - y1])
        scores.append(float(conf))

    indices = cv2.dnn.NMSBoxes(
        boxes_xywh,
        scores,
        score_threshold=0.0,
        nms_threshold=float(iou_thresh)
    )

    if len(indices) == 0:
        return []

    return [raw_boxes[i] for i in indices.flatten()]

# =========================
# ADAFACE PREPROCESS
# =========================
def preprocess_adaface(face_bgr):
    face = cv2.resize(face_bgr, (112, 112))
    face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
    face = face.astype(np.float32) / 255.0
    face = (face - 0.5) / 0.5
    face = np.transpose(face, (2, 0, 1))
    return face[None, ...]

def blur_score(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(g, cv2.CV_64F).var()

def expand_bbox(x1, y1, x2, y2, w, h, ratio=0.25):
    bw, bh = x2 - x1, y2 - y1
    pad = int(max(bw, bh) * ratio)
    return (
        max(0, x1 - pad),
        max(0, y1 - pad),
        min(w - 1, x2 + pad),
        min(h - 1, y2 + pad)
    )

# =========================
# RECOGNITION
# =========================
def identify_face(emb_norm: np.ndarray):
    """
    emb_norm: (D,) normalized
    returns: (best_name, best_score, second_score)
    """
    sims = db_mat @ emb_norm.astype(np.float32)  # (N,)
    order = np.argsort(sims)[::-1]
    best_i = int(order[0])
    best_score = float(sims[best_i])
    second_score = float(sims[int(order[1])]) if len(order) > 1 else -1.0
    return names[best_i], best_score, second_score

# =========================
# VIDEO LOOP
# =========================
cap = cv2.VideoCapture(VIDEO_SOURCE)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

print("\n[INFO] Running YOLO+AdaFace test. Press Q to quit.\n")

frame_idx = 0
fps_t0 = time.time()
fps = 0.0

while True:
    ok, frame = cap.read()
    if not ok:
        break

    frame_idx += 1
    H, W = frame.shape[:2]
    display = frame.copy()

    # FPS
    if frame_idx % 15 == 0:
        dt = time.time() - fps_t0
        fps = 15.0 / max(dt, 1e-6)
        fps_t0 = time.time()

    if frame_idx % RUN_EVERY_N_FRAMES != 0:
        cv2.putText(display, f"FPS: {fps:.1f}", (20, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
        cv2.imshow("YOLO Face + AdaFace Test", display)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
        continue

    # YOLO inference
    yolo_inp, scale, pad_x, pad_y = preprocess_yolo(frame)
    yolo_out = yolo_sess.run(None, {yolo_input_name: yolo_inp})

    raw_boxes = postprocess_yolo(
        yolo_out, H, W, scale, pad_x, pad_y, conf_thres=YOLO_CONF
    )
    boxes = apply_nms(raw_boxes, iou_thresh=YOLO_NMS_IOU)

    # For each detected face
    for (x1, y1, x2, y2, conf) in boxes:
        ex1, ey1, ex2, ey2 = expand_bbox(x1, y1, x2, y2, W, H, ratio=PAD_RATIO)
        face_crop = frame[ey1:ey2, ex1:ex2]
        if face_crop.size == 0:
            continue

        b = blur_score(face_crop)
        if b < MIN_BLUR:
            # draw but mark blurry
            cv2.rectangle(display, (x1, y1), (x2, y2), (0, 165, 255), 2)
            cv2.putText(display, f"BLUR {b:.0f}", (x1, y1 - 8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 165, 255), 2)
            continue

        # AdaFace embedding
        face_inp = preprocess_adaface(face_crop)
        emb = face_sess.run(None, {ada_input_name: face_inp})[0][0].astype(np.float32)
        emb = emb / (np.linalg.norm(emb) + 1e-9)

        best_name, best_score, second_score = identify_face(emb)
        margin = best_score - second_score

        if best_score >= ABSOLUTE_MIN_SCORE and margin >= MARGIN_THRES:
            label = f"{best_name} {best_score:.2f}"
            color = (0, 255, 0)
        else:
            label = f"Unknown {best_score:.2f}"
            color = (0, 0, 255)

        cv2.rectangle(display, (x1, y1), (x2, y2), color, 2)
        cv2.putText(display, label, (x1, y1 - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

    cv2.putText(display, f"FPS: {fps:.1f}", (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

    cv2.imshow("YOLO Face + AdaFace Test", display)
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
