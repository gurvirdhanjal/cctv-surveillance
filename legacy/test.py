import cv2
import os
import numpy as np
import onnxruntime as ort

# =========================
# PATHS
# =========================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

IMAGE_PATH = os.path.join(BASE_DIR, "employees", "deepak", "02.jpg")
SCRFD_ONNX = os.path.join(BASE_DIR, "models", "scrfd_2.5g.onnx")
ADAFACE_ONNX = os.path.join(BASE_DIR, "models", "adaface_ir50.onnx")

# =========================
# LOAD MODELS
# =========================
scrfd_sess = ort.InferenceSession(SCRFD_ONNX, providers=["CPUExecutionProvider"])
scrfd_input_name = scrfd_sess.get_inputs()[0].name

face_sess = ort.InferenceSession(ADAFACE_ONNX, providers=["CPUExecutionProvider"])

# =========================
# SCRFD PREPROCESS
# =========================
def preprocess_scrfd(img, size=640):
    h0, w0 = img.shape[:2]
    img_resized = cv2.resize(img, (size, size))
    img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
    img_rgb = img_rgb.astype(np.float32)
    img_rgb = (img_rgb - 127.5) / 128.0
    img_chw = np.transpose(img_rgb, (2, 0, 1))
    return img_chw[None], h0, w0

# =========================
# SCRFD DECODE
# =========================
def softmax(x):
    e = np.exp(x - np.max(x, axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def decode_scrfd(outputs, h0, w0,
                 input_size=640,
                 conf_thresh=0.6,
                 nms_thresh=0.35):

    strides = [8, 16, 32]

    cls_outputs  = outputs[0:3]
    bbox_outputs = outputs[3:6]

    boxes_all = []
    scores_all = []

    for cls_out, bbox_out, stride in zip(cls_outputs, bbox_outputs, strides):

        # shapes like:
        # cls_out  -> (N, 1)
        # bbox_out -> (N, 4)

        N = cls_out.shape[0]
        H = input_size // stride
        W = input_size // stride
        HW = H * W

        anchors_per_cell = N // HW
        assert anchors_per_cell * HW == N, "Anchor mismatch"

        # sigmoid confidence
        scores = 1 / (1 + np.exp(-cls_out[:, 0]))

        keep = scores > conf_thresh
        if not np.any(keep):
            continue

        scores = scores[keep]
        bbox = bbox_out[keep]

        # ---- GRID CENTERS (CORRECT) ----
        ys, xs = np.meshgrid(np.arange(H), np.arange(W))
        centers = np.stack([xs, ys], axis=-1).reshape(HW, 2)

        # repeat centers to match N (THIS IS THE FIX)
        centers = np.repeat(centers, anchors_per_cell, axis=0)

        centers = centers[keep] * stride

        x1 = centers[:, 0] - bbox[:, 0] * stride
        y1 = centers[:, 1] - bbox[:, 1] * stride
        x2 = centers[:, 0] + bbox[:, 2] * stride
        y2 = centers[:, 1] + bbox[:, 3] * stride

        boxes_all.append(np.stack([x1, y1, x2, y2], axis=1))
        scores_all.append(scores)

    if not boxes_all:
        return []

    boxes = np.concatenate(boxes_all)
    scores = np.concatenate(scores_all)

    # scale back to original image
    scale_x = w0 / input_size
    scale_y = h0 / input_size
    boxes[:, [0, 2]] *= scale_x
    boxes[:, [1, 3]] *= scale_y

    boxes_xywh = [
        [b[0], b[1], b[2] - b[0], b[3] - b[1]]
        for b in boxes
    ]

    idxs = cv2.dnn.NMSBoxes(
        boxes_xywh,
        scores.tolist(),
        conf_thresh,
        nms_thresh
    )

    if len(idxs) == 0:
        return []

    return [
        (*boxes[i].astype(int), float(scores[i]))
        for i in idxs.flatten()
    ]


# =========================
# ADAFACE PREPROCESS
# =========================
def preprocess_adaface(face):
    face = cv2.resize(face, (112, 112))
    face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
    face = face.astype(np.float32) / 255.0
    face = (face - 0.5) / 0.5
    face = np.transpose(face, (2, 0, 1))
    return face[None]

# =========================
# RUN
# =========================
img = cv2.imread(IMAGE_PATH)
if img is None:
    raise FileNotFoundError(IMAGE_PATH)

# ---- SCRFD inference ----
scrfd_inp, h0, w0 = preprocess_scrfd(img)
scrfd_out = scrfd_sess.run(None, {scrfd_input_name: scrfd_inp})
for i, o in enumerate(scrfd_out):
    print(f"output[{i}] shape:", o.shape)
final_boxes = decode_scrfd(scrfd_out, h0, w0)

print("Faces detected:", len(final_boxes))

# ---- AdaFace inference ----
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
        (x1, y1 - 8),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        (0, 255, 0),
        2
    )

print("Embeddings extracted:", len(embeddings))

cv2.imshow("SCRFD + AdaFace (Primary)", img)
cv2.waitKey(0)
cv2.destroyAllWindows()
