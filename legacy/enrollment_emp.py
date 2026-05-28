kimport cv2
import os
import time
import numpy as np
import onnxruntime as ort

# =========================
# CONFIG
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EMP_DIR = os.path.join(BASE_DIR, "employees")

YOLO_ONNX = os.path.join(BASE_DIR, "models", "yolov8s-face-lindevs.onnx")
ADAFACE_ONNX = os.path.join(BASE_DIR, "models", "adaface_ir50.onnx")

CAMERA_INDEX = 0
SAMPLES_REQUIRED = 6
CAPTURE_INTERVAL = 0.30   # seconds

MIN_FACE_SIZE = 50
MIN_BLUR = 35.0
PAD_RATIO = 0.30

os.makedirs(EMP_DIR, exist_ok=True)

# =========================
# LOAD MODELS
# =========================
yolo_sess = ort.InferenceSession(YOLO_ONNX, providers=["CPUExecutionProvider"])
face_sess = ort.InferenceSession(ADAFACE_ONNX, providers=["CPUExecutionProvider"])

yolo_input_name = yolo_sess.get_inputs()[0].name
ada_input_name = face_sess.get_inputs()[0].name

# =========================
# YOLO PREPROCESS
# =========================
def letterbox(img, new_shape=640, color=(114,114,114)):
    h, w = img.shape[:2]
    scale = min(new_shape / h, new_shape / w)
    nh, nw = int(h * scale), int(w * scale)
    img_resized = cv2.resize(img, (nw, nh))
    pad_y = (new_shape - nh) // 2
    pad_x = (new_shape - nw) // 2
    img_padded = cv2.copyMakeBorder(
        img_resized,
        pad_y, new_shape - nh - pad_y,
        pad_x, new_shape - nw - pad_x,
        cv2.BORDER_CONSTANT,
        value=color
    )
    return img_padded, scale, pad_x, pad_y

def preprocess_yolo(img):
    img_lb, scale, pad_x, pad_y = letterbox(img)
    img_rgb = cv2.cvtColor(img_lb, cv2.COLOR_BGR2RGB)
    img_norm = img_rgb.astype(np.float32) / 255.0
    img_chw = np.transpose(img_norm, (2,0,1))
    return img_chw[None], scale, pad_x, pad_y

# =========================
# YOLO POSTPROCESS
# =========================
def postprocess_yolo(output, orig_h, orig_w, scale, pad_x, pad_y, conf_thres=0.15):
    boxes = []
    preds = output[0][0].T  # (8400, 5)

    for det in preds:
        conf = float(det[4])
        if conf < conf_thres:
            continue

        cx, cy, bw, bh = det[:4]
        x1 = (cx - bw/2 - pad_x) / scale
        y1 = (cy - bh/2 - pad_y) / scale
        x2 = (cx + bw/2 - pad_x) / scale
        y2 = (cy + bh/2 - pad_y) / scale

        x1, y1, x2, y2 = map(int, [x1,y1,x2,y2])
        x1 = max(0, min(orig_w-1, x1))
        y1 = max(0, min(orig_h-1, y1))
        x2 = max(0, min(orig_w-1, x2))
        y2 = max(0, min(orig_h-1, y2))

        if x2-x1 < MIN_FACE_SIZE or y2-y1 < MIN_FACE_SIZE:
            continue

        boxes.append((x1,y1,x2,y2,conf))

    return boxes

def apply_nms(boxes, iou_thresh=0.45):
    if not boxes:
        return []
    b = [[x1,y1,x2-x1,y2-y1] for x1,y1,x2,y2,_ in boxes]
    s = [c for *_,c in boxes]
    idxs = cv2.dnn.NMSBoxes(b, s, 0.0, iou_thresh)
    return [boxes[i] for i in idxs.flatten()] if len(idxs) else []

# =========================
# ADAFACE PREPROCESS
# =========================
def preprocess_adaface(face):
    face = cv2.resize(face, (112,112))
    face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
    face = face.astype(np.float32)/255.0
    face = (face - 0.5) / 0.5
    face = np.transpose(face, (2,0,1))
    return face[None]

def blur_score(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(g, cv2.CV_64F).var()

def expand_bbox(x1,y1,x2,y2,w,h,r=0.3):
    bw, bh = x2-x1, y2-y1
    p = int(max(bw,bh)*r)
    return (
        max(0,x1-p), max(0,y1-p),
        min(w-1,x2+p), min(h-1,y2+p)
    )

# =========================
# INPUT
# =========================
emp = input("\nEnter employee name: ").strip()
if not emp:
    raise SystemExit("Invalid name")

emp_dir = os.path.join(EMP_DIR, emp)
os.makedirs(emp_dir, exist_ok=True)

# =========================
# CAMERA LOOP
# =========================
cap = cv2.VideoCapture(CAMERA_INDEX)
if not cap.isOpened():
    raise RuntimeError("Camera error")

print("\n[INFO] Auto-capturing 6 samples. Just look at camera.")

embs = []
count = 0
last_cap = 0

while count < SAMPLES_REQUIRED:
    ok, frame = cap.read()
    if not ok:
        break

    H,W = frame.shape[:2]
    disp = frame.copy()
    status = "NO FACE"

    y_inp, scale, px, py = preprocess_yolo(frame)
    y_out = yolo_sess.run(None, {yolo_input_name: y_inp})

    boxes = apply_nms(
        postprocess_yolo(y_out, H, W, scale, px, py)
    )

    if boxes:
        x1,y1,x2,y2,conf = max(
            boxes, key=lambda b:(b[2]-b[0])*(b[3]-b[1])
        )

        ex1,ey1,ex2,ey2 = expand_bbox(x1,y1,x2,y2,W,H)
        crop = frame[ey1:ey2, ex1:ex2]

        if crop.size:
            blur = blur_score(crop)
            if blur >= MIN_BLUR:
                now = time.time()
                status = f"CAPTURING {count}/{SAMPLES_REQUIRED}"

                if now-last_cap >= CAPTURE_INTERVAL:
                    last_cap = now
                    face_inp = preprocess_adaface(crop)
                    emb = face_sess.run(None, {ada_input_name: face_inp})[0][0]
                    emb = emb / (np.linalg.norm(emb)+1e-9)

                    embs.append(emb)
                    count += 1
                    cv2.imwrite(
                        os.path.join(emp_dir, f"{count:02d}.jpg"),
                        crop
                    )
                    print(f"✓ Captured {count}/{SAMPLES_REQUIRED}")

        cv2.rectangle(disp,(x1,y1),(x2,y2),(0,255,0),2)

    cv2.putText(disp, f"{emp}: {status}",
                (20,30), cv2.FONT_HERSHEY_SIMPLEX,
                0.8,(255,255,255),2)

    cv2.imshow("Enrollment", disp)
    if cv2.waitKey(1)&0xFF==ord("q"):
        break

cap.release()
cv2.destroyAllWindows()

# =========================
# SAVE DB
# =========================
if len(embs) < SAMPLES_REQUIRED:
    raise SystemExit("Enrollment incomplete")

db_path = os.path.join(BASE_DIR, "employee_db.npy")
db = np.load(db_path, allow_pickle=True).item() if os.path.exists(db_path) else {}

mean_emb = np.mean(np.vstack(embs), axis=0)
mean_emb /= np.linalg.norm(mean_emb)

db[emp] = mean_emb
np.save(db_path, db)

print(f"\n✅ {emp} enrolled successfully")
