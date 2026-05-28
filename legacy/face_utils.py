import cv2
import numpy as np
import onnxruntime as ort


class FaceRecognizerONNX:
    def __init__(
        self,
        scrfd_onnx_path,
        adaface_onnx_path,
        conf_thres=0.6,
        nms_thres=0.35,
        min_face_size=40,
        providers=["CPUExecutionProvider"],
    ):
        self.conf_thres = conf_thres
        self.nms_thres = nms_thres
        self.min_face_size = min_face_size

        # SCRFD detector
        self.det_sess = ort.InferenceSession(
            scrfd_onnx_path, providers=providers
        )
        self.det_input_name = self.det_sess.get_inputs()[0].name

        # AdaFace embedder (UNCHANGED)
        self.face_sess = ort.InferenceSession(
            adaface_onnx_path, providers=providers
        )

    # =========================
    # SCRFD PREPROCESS
    # =========================
    def _preprocess_scrfd(self, img, size=640):
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
    def _decode_scrfd(
        self,
        outputs,
        h0,
        w0,
        input_size=640,
    ):
        """
        Decodes SCRFD outputs into (x1, y1, x2, y2, conf)
        This version matches flattened SCRFD ONNX:
        cls:  (N, 1)
        bbox: (N, 4)
        """

        strides = [8, 16, 32]

        cls_outputs = outputs[0:3]
        bbox_outputs = outputs[3:6]

        boxes_all = []
        scores_all = []

        for cls_out, bbox_out, stride in zip(cls_outputs, bbox_outputs, strides):

            # cls_out  -> (N, 1)
            # bbox_out -> (N, 4)
            N = cls_out.shape[0]

            H = input_size // stride
            W = input_size // stride
            HW = H * W

            anchors_per_cell = N // HW
            if anchors_per_cell * HW != N:
                continue

            # sigmoid confidence
            scores = 1.0 / (1.0 + np.exp(-cls_out[:, 0]))

            keep = scores > self.conf_thres
            if not np.any(keep):
                continue

            scores = scores[keep]
            bbox = bbox_out[keep]

            # grid centers
            ys, xs = np.meshgrid(np.arange(H), np.arange(W))
            centers = np.stack([xs, ys], axis=-1).reshape(HW, 2)
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

        # NMS
        boxes_xywh = [
            [b[0], b[1], b[2] - b[0], b[3] - b[1]]
            for b in boxes
        ]

        idxs = cv2.dnn.NMSBoxes(
            boxes_xywh,
            scores.tolist(),
            self.conf_thres,
            self.nms_thres,
        )

        if len(idxs) == 0:
            return []

        final = []
        for i in idxs.flatten():
            x1, y1, x2, y2 = boxes[i].astype(int)

            # minimum face size filter
            if (x2 - x1) < self.min_face_size or (y2 - y1) < self.min_face_size:
                continue

            final.append((x1, y1, x2, y2, float(scores[i])))

        return final

    # =========================
    # ADAFACE PREPROCESS (UNCHANGED)
    # =========================
    def _preprocess_adaface(self, face):
        face = cv2.resize(face, (112, 112))
        face = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
        face = face.astype(np.float32)
        face = (face - 127.5) / 128.0
        face = np.transpose(face, (2, 0, 1))
        return face[None]


    # =========================
    # PUBLIC API (UNCHANGED)
    # =========================
    def detect_and_extract(self, frame):
        """
        Args:
            frame (np.ndarray): BGR image

        Returns:
            list of dict:
                {
                    "bbox": (x1, y1, x2, y2),
                    "conf": float,
                    "embedding": np.ndarray (512,)
                }
        """

        # ---- SCRFD DETECTION ----
        det_inp, h0, w0 = self._preprocess_scrfd(frame)
        outputs = self.det_sess.run(None, {self.det_input_name: det_inp})

        final_boxes = self._decode_scrfd(outputs, h0, w0)

        # ---- ADAFACE EMBEDDING (UNCHANGED) ----
        results = []
        for x1, y1, x2, y2, conf in final_boxes:
            face_crop = frame[y1:y2, x1:x2]
            if face_crop.size == 0:
                continue

            face_inp = self._preprocess_adaface(face_crop)
            emb = self.face_sess.run(None, {"input": face_inp})[0][0]

            results.append({
                "bbox": (x1, y1, x2, y2),
                "conf": conf,
                "embedding": emb
            })

        return results
    
    def detect_faces_only(self, frame):
        det_inp, h0, w0 = self._preprocess_scrfd(frame)
        outputs = self.det_sess.run(None, {self.det_input_name: det_inp})
        final_boxes = self._decode_scrfd(outputs, h0, w0)
        return final_boxes
