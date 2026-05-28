import cv2
import os
import numpy as np
import onnxruntime as ort

# =========================
# PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_PATH = os.path.join(BASE_DIR, "employees", "gurvir", "04.jpg")
YOLO_ONNX = os.path.join(BASE_DIR, "models", "yolov8s-face-lindevs.onnx")
ADAFACE_ONNX = os.path.join(BASE_DIR, "models", "adaface_ir50.onnx")

# =========================
# LOAD MODELS
# =========================
yolo_sess = ort.InferenceSession(YOLO_ONNX, providers=["CPUExecutionProvider"])
face_sess = ort.InferenceSession(ADAFACE_ONNX, providers=["CPUExecutionProvider"])

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
# YOLO POSTPROCESS
# =========================
def postprocess_yolo(output, orig_h, orig_w, scale, pad_x, pad_y, conf_thres=0.15):
    raw_boxes = []

    preds = output[0][0].T  # (8400, 5)

    for det in preds:
        conf = float(det[4])
        if conf < conf_thres:
            continue

        cx, cy, bw, bh = det[:4]

        # coords already in 640-space pixels
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

        if x2 - x1 < 20 or y2 - y1 < 20:
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
        scores.append(conf)

    indices = cv2.dnn.NMSBoxes(
        boxes_xywh,
        scores,
        score_threshold=0.0,
        nms_threshold=iou_thresh
    )

    if len(indices) == 0:
        return []

    return [raw_boxes[i] for i in indices.flatten()]


# =========================
# ADAFACE PREPROCESS
# =========================
def preprocess_adaface(face):
    face = cv2.resize(face, (112, 112))
    face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
    face = face.astype(np.float32) / 255.0
    face = (face - 0.5) / 0.5
    face = np.transpose(face, (2, 0, 1))
    return face[None, ...]


# =========================
# RUN
# =========================
img = cv2.imread(IMAGE_PATH)
if img is None:
    raise FileNotFoundError(IMAGE_PATH)

# YOLO inference
yolo_inp, scale, pad_x, pad_y = preprocess_yolo(img)
yolo_out = yolo_sess.run(None, {"images": yolo_inp})

raw_boxes = postprocess_yolo(
    yolo_out,
    img.shape[0],
    img.shape[1],
    scale,
    pad_x,
    pad_y,
    conf_thres=0.15
)

final_boxes = apply_nms(raw_boxes, iou_thresh=0.45)

print("Faces detected:", len(final_boxes))

# AdaFace inference
embeddings = []

for (x1, y1, x2, y2, conf) in final_boxes:
    face_crop = img[y1:y2, x1:x2]
    if face_crop.size == 0:
        continue

    face_inp = preprocess_adaface(face_crop)
    emb = face_sess.run(None, {"input": face_inp})[0][0]
    embeddings.append(emb)

    cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
    cv2.putText(
        img,
        f"{conf:.2f}",
        (x1, y1 - 10),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0),
        2
    )

print("Embeddings extracted:", len(embeddings))

cv2.imshow("YOLO + AdaFace ONNX", img)
cv2.waitKey(0)
cv2.destroyAllWindows()
