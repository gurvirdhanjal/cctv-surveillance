# VMS ML Architecture — Decisions, Rationale, and Technical Reference

> **Purpose:** This document records every major ML/AI architectural decision made in the VMS
> system, explains each technique in plain language, explains why each choice was made, and
> explicitly documents what was considered and rejected and why. Use this as a reference when
> defending technical choices or comparing approaches with others.

---

## Part 1: Glossary — Every Term Explained

Before the decisions, here is what every technical term actually means, in plain language.

---

### SOTA (State of the Art)
The best publicly known result on a benchmark dataset at a given point in time. When a paper
says their model is "SOTA on LFW" it means it achieves the highest published accuracy on the
Labeled Faces in the Wild dataset. SOTA is not a brand name — it is a moving target. A model
that is SOTA in 2022 may be mediocre by 2025. When this document says "SOTA," it means the
model ranked at or near the top of the relevant academic benchmark at the time of selection.

### mAP (Mean Average Precision)
A single number that summarises how well a detection model finds objects across different
confidence thresholds. It answers: "if I vary how confident the model needs to be before it
calls something a detection, what is the average precision?" A 96% mAP means the model is
nearly always right when it fires, across all confidence levels. mAP is the standard metric
for object detection (YOLO, SCRFD etc.) — not for classification or Re-ID.

### Precision vs Recall
- **Precision:** of everything the model flagged as a detection, what fraction was actually correct?
  High precision = few false alarms.
- **Recall:** of everything that actually was a detection target, what fraction did the model find?
  High recall = few missed detections.
- These trade off against each other. Raising a confidence threshold improves precision but
  lowers recall. Lowering it does the reverse.

### F1 Score
The harmonic mean of precision and recall: `2 * (P * R) / (P + R)`. It is one number that
captures both. A model that achieves 100% precision but 0% recall has F1 = 0. F1 is especially
useful when classes are imbalanced (much more negative data than positive) because overall
accuracy becomes misleading.

### AUC (Area Under the ROC Curve)
ROC = Receiver Operating Characteristic curve, which plots true positive rate vs false positive
rate at every possible threshold. AUC = the area under that curve. AUC = 1.0 is a perfect
classifier; AUC = 0.5 is random guessing. It measures the model's ability to rank positives
above negatives, independent of any specific threshold choice. Used heavily in medical ML
(cancer detection, etc.) because choosing a threshold is a clinical decision separate from
model quality.

### Embedding / Feature Vector
A list of numbers (a vector) that represents something — a face, a body, a piece of text — in
a way that captures meaning. In face recognition, a 512-dimensional embedding means the model
compressed an entire face image into 512 numbers such that two photos of the same person have
similar vectors, and photos of different people have dissimilar vectors. "Embedding space" is
the mathematical space all these vectors live in.

### Cosine Similarity
A way to measure how similar two vectors are, ranging from -1 (completely opposite) to 1
(identical direction). In face recognition, two embeddings with cosine similarity > 0.72 are
judged to be the same person. The threshold (0.72 in this system) is a calibration decision —
it is not a law of nature. Cosine similarity ignores magnitude; only direction matters. This is
why it works well for embeddings, which are often L2-normalised.

### L2 Normalisation
Rescaling a vector so its length (L2 norm) is exactly 1.0. After L2 normalisation, cosine
similarity equals dot product, which is computationally cheaper. Most modern embedding models
(AdaFace, TransReID) output L2-normalised embeddings as a design choice.

### Transfer Learning
Taking a model already trained on a large dataset (e.g., ImageNet with 1.2M images) and
fine-tuning it on a smaller, specific dataset. The model starts with learned features (edges,
textures, shapes) from the large dataset rather than random weights. This is why "14 CNN
architectures using transfer learning" in the resume is standard practice — it would be
unusual NOT to use transfer learning. The alternative (training from random weights on 6,000
images) would perform much worse.

### Fine-tuning
A specific form of transfer learning where you continue training a pre-trained model on your
target data, usually with a small learning rate so the pre-trained weights are adjusted rather
than overwritten. Fine-tuning on plant-floor specific data would be the path to further accuracy
improvement beyond off-the-shelf models.

### Quantisation
Representing model weights with fewer bits to reduce memory and speed up computation.
- **FP32:** 32-bit floating point — the default training precision.
- **FP16:** 16-bit floating point — half the memory, ~2× faster on modern GPUs, negligible
  accuracy loss for inference (< 0.5% typically).
- **INT8:** 8-bit integer — quarter the memory, ~4× faster, but requires a calibration dataset
  to preserve accuracy. Typical accuracy loss is 1–2%.
- **INT4:** 4-bit — used in LLMs, not standard for CV models yet.

### Pruning
Removing weights from a neural network that contribute little to the output. A pruned model is
smaller and faster but requires retraining to recover accuracy. Structured pruning removes
entire channels or layers; unstructured pruning removes individual weights. Pruning a pre-trained
model you didn't train requires the original training code, training data, and significant
engineering effort.

### TensorRT (TRT)
NVIDIA's inference optimisation library. It takes an ONNX model, analyses the computation
graph, fuses operations, selects optimised CUDA kernels, and optionally converts to FP16 or INT8.
The output is a compiled `.trt` engine file specific to your GPU model and batch size. TensorRT
typically delivers 2–10× speedup over plain ONNX Runtime on NVIDIA GPUs.

### ONNX (Open Neural Network Exchange)
A standard file format for ML models. Frameworks (PyTorch, TensorFlow, etc.) can export to
ONNX, and runtimes (ONNX Runtime, TensorRT, Triton) can load it. ONNX is the lingua franca
that lets you train in PyTorch and serve in TensorRT without rewriting anything.

### ONNX Runtime (ORT)
Microsoft's inference engine for ONNX models. Supports CPU, CUDA, TensorRT, DirectML execution
providers. In this system, ORT is the default backend; TensorRT is an opt-in execution provider
within ORT, not a separate binary.

### Triton Inference Server
NVIDIA's production model serving system. It hosts multiple models, handles batching across
concurrent requests, supports gRPC and HTTP, manages GPU memory, and enables horizontal scaling
(multiple Triton instances behind a load balancer). The key property for this system: with
Triton, going from 12 to 52 to 100 cameras requires only configuration changes, not code
changes.

### Bayesian Hyperparameter Optimisation
A method for finding optimal hyperparameters (thresholds, learning rates, regularisation
coefficients) that is smarter than grid search. Grid search exhaustively tries every combination
in a predefined grid. Bayesian optimisation builds a probabilistic model of "which parameter
regions have been good so far" and samples the next point from the most promising region. It
finds good solutions in far fewer evaluations. Libraries: Optuna, Hyperopt, Ax.

### Grid Search
Exhaustively trying every combination in a predefined parameter grid. If you have 3 thresholds
each with 10 possible values, grid search runs 10³ = 1,000 experiments. Bayesian optimisation
achieves comparable results in ~50–100 experiments.

### SMOTE (Synthetic Minority Oversampling TEchnique)
A technique for handling class imbalance. Instead of just duplicating minority-class samples
(oversampling), SMOTE generates synthetic new samples by interpolating between existing
minority-class samples in feature space. Useful when one class has far fewer examples than
another — e.g., anomaly detection where normal frames vastly outnumber anomalous ones.

### Class Imbalance
When the dataset has many more samples of one class than another. A model trained on 99% normal
/ 1% anomaly data will learn to always predict "normal" and achieve 99% accuracy while detecting
nothing. F1 score or class-weighted loss functions are the correct metrics and training
objectives in this case.

### Stacked Ensemble
A two-stage model combination: Stage 1 trains N base models (e.g., XGBoost, Random Forest,
SVM). Stage 2 trains a meta-model (often logistic regression) on the predictions of the Stage 1
models, learning how to combine them. Stacked ensembles excel on tabular structured data where
individual models capture different patterns. They are less common in deep learning / computer
vision, where the neural network already learns its own internal ensemble of features.

### Random Forest
An ensemble of many decision trees, each trained on a random subset of features and data.
Predictions are averaged across trees. Random Forest is robust, interpretable, and works well on
tabular data. It does not process images directly — it requires hand-crafted features.

### XGBoost (Extreme Gradient Boosting)
A gradient-boosted tree algorithm that builds trees sequentially, each correcting the errors of
the previous. Often the best performer on tabular/structured data problems (finance, medical
records, sensor data). Not a vision model.

### SVM (Support Vector Machine)
A classical classifier that finds the hyperplane in feature space that maximally separates
classes. Still useful for small datasets or as a final classification head on top of embeddings.
Was the standard face verification method before deep learning.

### RFE (Recursive Feature Elimination)
A feature selection method: train a model, rank features by importance, remove the least
important, retrain, repeat. Useful when your input has many potentially redundant features
(e.g., clinical measurements, sensor readings). Not meaningful for embeddings from deep networks,
because the dimensions are entangled and removing any subset distorts the embedding space.

### Anchor-Free Detection
Traditional object detectors (YOLO v1–v3, Faster R-CNN) place predefined anchor boxes at every
location and predict adjustments to these anchors. Anchor-free detectors (SCRFD, CenterFace,
FCOS) directly predict object centres and sizes without anchors. Anchor-free models are simpler
to train, easier to generalise to new scales, and are the current dominant approach in face
detection.

### Affine Alignment (5-Point)
In face recognition, aligning a face crop to a canonical template before embedding it.
SCRFD-10G detects 5 facial keypoints (left eye, right eye, nose, left mouth corner, right mouth
corner). Affine alignment uses these 5 points to warp the face into a standard position and
scale before feeding it to AdaFace. This eliminates pose variation as a confound and is critical
for accuracy with the IR101/WebFace12M model.

### Re-ID (Re-Identification)
The task of recognising the same person across different camera views, different times, or
after they have left and re-entered the frame. Re-ID models output body embeddings similar to
face embeddings — the same person should have similar body embeddings regardless of camera angle.

### FAISS (Facebook AI Similarity Search)
A library for fast nearest-neighbour search in embedding spaces. Given a query embedding, FAISS
finds the most similar embeddings in a database of millions in milliseconds. It is used here
as the search index for face and body Re-ID — when a new detection arrives, FAISS finds the
closest known person embedding. FAISS is an index (cache), not a database. PostgreSQL is the
source of truth.

### FSM (Finite State Machine)
A computational model that moves between a fixed set of states based on events. In this system,
an alert FSM tracks whether an anomaly condition (e.g., loitering) has been active long enough
to fire an alert, is suppressed during a deduplication window, or has cleared. The FSM prevents
alert flooding from the same ongoing event.

### Kalman Filter
A mathematical algorithm that estimates the state of a system (e.g., position and velocity of
a person) from noisy measurements over time. Given "person X was at position P at time T", the
Kalman filter predicts where they should be at time T+n. Used in this system to gate cross-
camera identity merges: if a person's predicted position (given known camera topology) is
implausible, the merge is rejected.

### BoT-SORT
Byte Track + SORT (Simple Online and Realtime Tracking) with IoU-based association, Kalman
filter trajectory prediction, and optional camera-motion compensation (GMC). Tracks person
bounding boxes across frames within a single camera, assigning consistent track IDs. Operates
at the intra-camera level; cross-camera identity is handled by the Re-ID layer.

### ICS (Identity Consistent Sampling)
A training technique from the TransReID-SSL paper. During contrastive pre-training, ICS ensures
that image crops from the same identity are consistently sampled together, building stronger
identity-discriminative representations. Models trained with ICS generalise better across
viewpoints than standard contrastive training.

### MSMT17
A large-scale person Re-ID benchmark dataset: 126,441 images of 4,101 identities across 15
cameras in a campus environment with varying lighting conditions (morning, noon, afternoon,
overcast). It is the standard benchmark for evaluating body Re-ID models intended for
unconstrained real-world deployment. MSMT17 is harder than earlier benchmarks (Market-1501,
DukeMTMC) because it has more cameras and more lighting variation.

### WebFace12M
A large-scale face dataset of 12 million images of 617,970 identities, collected from the web
with automated cleaning. AdaFace IR101 trained on WebFace12M is the current SOTA face
recognition model for real-world deployment. Larger and cleaner than the VGGFace2 / MS-Celeb
datasets used by older AdaFace and ArcFace models.

---

## Part 2: The VMS ML Stack — Every Component Explained

---

### 2.1 Face Detection — SCRFD-10G-KPS

**What it does:** Takes a camera frame and outputs bounding boxes around every face, plus
5 facial keypoints (landmarks) per face. The keypoints enable affine alignment.

**Why SCRFD-10G-KPS:**
SCRFD (Sample and Computation Redistribution for Face Detection) from InsightFace is an
anchor-free face detector trained on WIDER FACE. SCRFD-10G is the 10 GFLOPs variant — large
enough for high accuracy, small enough for real-time operation. The KPS suffix means keypoint
output is included.

Key benchmarks that drove selection:
- WIDER FACE Hard subset: 90.3% AP — SOTA at time of selection
- Runs at real-time on GPU with TensorRT FP16
- Anchor-free: no anchor tuning required for deployment
- Native 5-point keypoint output: enables affine alignment for AdaFace without a separate
  landmark model

**What was rejected and why:**

| Alternative | Why Rejected |
|---|---|
| RetinaFace | Older InsightFace detector; lower Hard-set AP than SCRFD. Same code family, strictly inferior. |
| MTCNN | Three-stage cascade, much slower, lower accuracy on small/occluded faces. Standard in 2018, obsolete by 2022. |
| YOLOv8-Face | Strong but does not produce keypoints in the standard 5-point format without additional head modification. Would break the affine alignment pipeline. |
| Custom CNN from scratch | Would require a massive face dataset (millions of images) and months of training to approach SCRFD's performance. No justification. |
| Haar Cascades | OpenCV classic. Obsolete. Cannot detect partially occluded, angled, or small faces reliably. |

**Key implementation details:**
- Model has 9 output tensors (confirmed by inspection). Outputs are pre-sigmoid — sigmoid must
  NOT be applied in `_decode`. Previous implementations that applied sigmoid here degraded all
  detection scores.
- Uses letterbox resize (not stretch), with a single `det_scale` scalar to map detections
  back to original resolution.
- Confidence threshold is config-driven: `VMS_SCRFD_CONF` — never hardcoded.

---

### 2.2 Face Recognition / Embedding — AdaFace IR101 / WebFace12M

**What it does:** Takes an aligned face crop (112×112 pixels, RGB) and outputs a 512-
dimensional L2-normalised embedding. Two embeddings from the same person have high cosine
similarity; embeddings from different people have low cosine similarity.

**Why AdaFace IR101 / WebFace12M:**
AdaFace introduced adaptive margin loss — the training loss margin adapts per sample based on
image quality. High-quality face images get a large margin (harder training signal); low-quality
images get a smaller margin (gentler signal). This makes the model significantly more robust to
blurry, low-light, and partially occluded faces — exactly the conditions found in plant-floor
surveillance.

IR101 is the ResNet-101 with an identity residual (IR) modification, the backbone used in
most SOTA face recognition models since ArcFace. WebFace12M is the 12-million-image training
dataset — larger and cleaner than MS-Celeb-1M (retired due to privacy concerns) and VGGFace2.

AdaFace IR101/WebFace12M performance on IJB-C (the hardest public face verification benchmark):
TAR @ FAR=1e-4 = 97.72% — SOTA at time of selection.

**The CVLFace preprocessing requirement:**
The deployed model is from the CVLFace repository. CVLFace models expect RGB input (not BGR).
BGR→RGB conversion is applied in `_preprocess`. If the original AdaFace IR50 model is ever
swapped back in, this conversion must be removed. This is a critical, non-obvious requirement
documented as a gotcha in CLAUDE.md.

**What was rejected and why:**

| Alternative | Why Rejected |
|---|---|
| ArcFace IR50 | AdaFace IR101 outperforms ArcFace at every operating point on IJB-C. IR50 is smaller but less accurate. Selected model is already production-size. |
| FaceNet (Google) | 2015 model. 128-dim embedding. Significantly lower accuracy than any modern angular-margin method. Mentioned frequently because it was widely used; it is now obsolete. |
| DeepFace (Facebook) | Research prototype, not a standalone deployable model. |
| VGGFace / VGGFace2 | Older training data, lower performance. ArcFace/AdaFace on WebFace12M strictly dominates. |
| Training a custom face recognition model | Requires millions of labelled face identity images. Off-the-shelf AdaFace on WebFace12M already covers every demographic and lighting condition. Custom training would be strictly worse unless you have a very specific domain shift (e.g., faces always covered by PPE masks — a separate problem). |
| Dlib face_recognition | Uses ResNet-34 trained on a private dataset. Reasonable for hobby projects, significantly below SOTA on hard benchmarks. |

**The `adaface_min_sim = 0.72` calibration issue:**
The 0.72 threshold was set for the older IR50/MS1MV2 model on unaligned crops. After upgrading
to IR101/WebFace12M with affine alignment, the embedding distribution shifts. Affine-aligned
IR101 embeddings cluster more tightly for the same person AND more separately for different
people, meaning both the match threshold and the non-match threshold should shift. This
re-calibration requires real plant-floor footage and is a mandatory `/advisor` trigger before
any change.

---

### 2.3 Person Tracking — YOLO11 + BoT-SORT

**What it does:** Detects person bounding boxes in each frame (YOLO) and links them across
frames with consistent track IDs (BoT-SORT). This is intra-camera tracking — the same person
in the same camera gets the same track ID as they move across the frame.

**Why YOLO + BoT-SORT:**
YOLO (You Only Look Once) is a single-pass anchor-based (YOLOv1–v5) or anchor-free (YOLO11)
object detector. It is the industry standard for real-time person detection due to its speed/
accuracy trade-off. YOLO11 is the current generation, trained on COCO (80 classes including
person).

BoT-SORT (Byte Track + SORT) is a multi-object tracker that combines:
- Kalman filter trajectory prediction
- IoU-based assignment (match detections to existing tracks by bounding box overlap)
- Byte-level association (keep low-confidence detections in play for one frame to handle
  occlusions gracefully)
- Optional GMC (Global Motion Compensation) for camera movement — disabled for fixed
  plant-floor cameras

**What was rejected and why:**

| Alternative | Why Rejected |
|---|---|
| DeepSORT | Older tracker that uses a Re-ID appearance model in the association step. Slower. BoT-SORT achieves higher MOTA/IDF1 on MOT benchmarks without the Re-ID dependency in the tracker itself. |
| SORT (Simple SORT) | No byte-level association; loses tracks in occlusions. BoT-SORT is a strict superset. |
| StrongSORT | Higher accuracy on MOT20 but higher compute. BoT-SORT sufficient for the frame rates and camera counts here. |
| OpenPose for tracking | Pose estimation, not tracking. Different task. |
| Centroid-based trackers | Too simple; fail on occlusion and crossing paths. |

**Key config:**
- `VMS_TRACKER_BUFFER_FRAMES` controls how many frames a track is kept alive after a detection
  gap. Made config-driven to allow per-deployment tuning without code changes.

---

### 2.4 Body Re-ID — TransReID-SSL ViT-B/16+ICS (MSMT17) + OSNet AIN

**What it does:** Produces a body appearance embedding for a detected person crop. Used when
face is unavailable (poor angle, occlusion, distance). Cross-camera identity linking for unknown
persons relies entirely on body Re-ID.

**Why TransReID-SSL ViT-B/16+ICS (MSMT17):**
TransReID-SSL is a transformer-based Re-ID model from Alibaba DAMO Academy. Key reasons for
selection:
1. **ViT backbone:** Vision Transformer (ViT) captures global appearance patterns (gait,
   clothing colour distribution, body proportions) that CNN-based Re-ID models miss because
   CNNs are inherently local-feature models.
2. **ICS (Identity Consistent Sampling):** Training procedure that builds stronger cross-view
   identity representations.
3. **MSMT17 supervised fine-tuning:** 75.1 mAP / 89.6 R1 on MSMT17 — SOTA at time of
   selection for a deployable model.
4. **256×128 input:** Standard Re-ID input resolution, compatible with the BoT-SORT bounding
   box crops.

**The pose-normalised torso crop:**
Before passing a detection to TransReID, the crop is warped using pose keypoints to align the
torso. This addresses a core failure mode: a person facing left and the same person facing right
would have different raw crops but near-identical pose-normalised torso crops, improving cross-
camera match rates.

**OSNet AIN MSMT17:**
OSNet (Omni-Scale Network) is a lightweight CNN-based Re-ID model. AIN = Attentive Instance
Normalisation. Used as a secondary body Re-ID model in the ensemble path, particularly for
cases where the ViT model produces low-quality embeddings. OSNet was exported to ONNX in
Phase 6c and validated for cosine drift between FP32 and FP16 (< 0.01 on test crops).

**What was rejected and why:**

| Alternative | Why Rejected |
|---|---|
| OSNet alone (without TransReID) | Pure CNN; misses global appearance patterns. 4–6% lower mAP on MSMT17 than TransReID. |
| FastReID | Meta's Re-ID framework, good results, but the specific model weights for MSMT17 ViT are less accessible. TransReID-SSL was directly available as pre-trained weights. |
| DukeMTMC-based models | DukeMTMC dataset officially retracted in 2019 due to consent/privacy issues. Any model trained on DukeMTMC carries legal risk. Explicitly excluded. |
| Market-1501-based models | Smaller dataset (1,501 identities), easier domain, lower benchmark numbers. MSMT17 is the harder and more representative benchmark. |
| Custom Re-ID model | Would need a multi-camera footage dataset from the actual plant floor with identity labels. Not feasible at deployment time. Off-the-shelf MSMT17 model is the correct starting point. |
| `vit_base_ics_cfs_lup.pth` (SSL backbone only) | This is the self-supervised pre-training checkpoint — it has no classifier head, no identity labels, and cannot produce Re-ID embeddings without supervised fine-tuning. Named similarly to the supervised model but fundamentally different. Explicitly documented as a gotcha. |

**Calibrated thresholds (from 2026-06-16 webcam session):**
- `reid_body_confirmed_sim = 0.65` (same person, high confidence)
- `reid_body_cross_cam_sim = 0.70` (cross-camera match threshold, stricter)

These must be re-calibrated on real plant-floor cameras before tightening.

---

### 2.5 Action Recognition — R(2+1)D-18

**What it does:** Classifies short video clips into action categories (e.g., walking, fighting,
falling). Used to support the violence anomaly detector.

**Why R(2+1)D-18:**
R(2+1)D decomposes 3D convolutions (which process space and time together) into separate 2D
spatial and 1D temporal convolutions. This provides:
- Lower compute than full 3D convolutions (C3D, I3D)
- Faster inference than two-stream optical flow networks
- Pre-trained on Kinetics-400 (400 action classes, ~300K video clips)
- Stable ONNX export with static input shapes — critical for TensorRT and Triton compatibility

A warm-up pass runs after TRT engine load to avoid cold-cache latency on the first clip.

**Why MoViNet was rejected:**
MoViNet (Mobile Video Network, Google) uses a causal stream buffer architecture — the model
maintains a running state across frames rather than processing fixed-length clips. This dynamic
state makes the model incompatible with:
- Triton's static batching requirement (Phase 6c)
- ONNX export with static input shapes for TensorRT caching
- Deterministic replay for audit purposes

MoViNet was initially integrated and then formally removed in Phase 6c Task 8 based on this
incompatibility analysis.

---

### 2.6 PPE Detection — SH17 YOLOv8-Large

**What it does:** Detects personal protective equipment items on detected persons: helmet,
safety vest, gloves, face mask, and others. Used to trigger PPE compliance anomaly alerts.

**Why SH17 YOLOv8-Large:**
SH17 is a PPE-specific detection dataset. YOLOv8-Large provides sufficient accuracy for
workplace PPE compliance without requiring a custom training run. The model activates
conditionally via `VMS_PPE_MODEL` environment variable — it adds GPU load only when PPE
compliance is enabled.

**Critical implementation note — SH17 class indices:**
These are non-obvious and must never be changed without re-verifying against the model:
- Helmet = class index 10
- Safety vest = class index 16
- Gloves = class index 9
- Face mask = class index 5

---

## Part 3: GPU Acceleration Architecture

---

### 3.1 The TensorRT FP16 Decision

**The choice:** All four inference models (SCRFD, AdaFace, TransReID, PPE/YOLO) run through
TensorRT Execution Provider within ONNX Runtime, in FP16 precision.

**Why FP16, not INT8:**
- FP16 requires no calibration dataset — the conversion is mathematically exact up to rounding.
  A calibration dataset for INT8 must cover the full expected input distribution; poor calibration
  causes accuracy degradation on out-of-distribution inputs (e.g., unusual lighting, partial occlusion).
- FP16 cosine drift gate: measured at ≥0.99 cosine similarity between FP32 and FP16 embeddings.
  This is the identity correctness gate (§6.1 in the GPU spec). If any crop scores below 0.99,
  the deployment fails the gate.
- INT8 is deferred to Phase 6d, which only triggers if CPU decode shows ≥10ms/frame after motion
  gate savings at 52+ camera scale. It is not needed for the current 12-camera MVP.

**Why TensorRT over plain ONNX Runtime CUDA:**
- TRT fuses operations that ORT would run separately (e.g., BatchNorm + ReLU fused into one kernel)
- TRT selects the fastest available CUDA kernel for each operation on your specific GPU
- TRT caches the compiled `.trt` engine, so subsequent runs start instantly
- Measured result: **27× speedup at 5-camera load; 1,125 MB VRAM**

**The cold-cache problem:**
On first run, TRT builds the engine (compilation takes 30–120 seconds per model). Subsequent
runs load the cached `.trt` file in ~1 second. Cold-cache startup time is logged explicitly
so operators understand the delay.

**Startup assertion:**
If TensorRT EP silently falls back to CPU (a common misconfiguration on systems where
`nvinfer.dll` / `libnvinfer.so` is not on PATH), the engine logs a loud warning. Before this
guard, silent CPU fallback caused unexplained 10× performance degradation with no error message.

---

### 3.2 Triton Inference Server (Phase 6c)

**The problem it solves:** As camera count grows, multiple concurrent inference requests
arrive simultaneously. With direct ORT, each camera thread competes for the same GPU context.
Triton serialises these requests, batches them where possible, and manages GPU memory centrally.

**Architecture:**
```
Camera N → IngestionWorker → Redis Stream → InferenceEngine
                                                   │
                                    InferenceBackend (protocol)
                                        /               \
                            OrtInferenceBackend    TritonInferenceBackend
                              (default)              (VMS_INFERENCE_BACKEND=triton)
                                                          │
                                              gRPC → Triton Server
                                                          │
                                              SCRFD / AdaFace / TransReID / YOLO
```

**`InferenceBackend` protocol:**
A Python Protocol (structural interface) that defines `infer(model_name, inputs) → outputs`.
Both ORT and Triton adapters implement this protocol. The InferenceEngine instantiates the
correct backend based on config at startup. Switching backends requires only a `.env` change.

**The model-repo generator:**
`build_triton_repo.py` inspects an ONNX graph's IO signatures (tensor names, shapes, dtypes)
and automatically generates `config.pbtxt` — the Triton model configuration file. This
eliminates manual config.pbtxt authoring, which is error-prone and must be regenerated
whenever a model is updated.

**Fixed-batch detection:**
Models with a static batch dimension in their ONNX graph (fixed-batch models) are automatically
detected by the generator and given `max_batch_size = 0` in config.pbtxt (Triton's way of
saying "batch size is baked into the model"). Dynamic-batch models get `max_batch_size = N`.

**The scaling promise:**
After Phase 6c: going from 12 → 52 → 100 cameras requires only:
1. Adding camera rows to the `cameras` DB table
2. Setting `VMS_INFERENCE_BACKEND=triton` in `.env` and pointing at the Triton host
3. No Python code changes anywhere

---

## Part 4: Identity Architecture

---

### 4.1 The Identity Fusion Strategy

**The choice:** Rule-based priority fusion: Face ≻ Body ≻ BLE.
- If face cosine similarity exceeds `adaface_min_sim` AND face quality is above
  `reid_face_quality_floor` → resolve via face
- Else if body cosine similarity exceeds `reid_body_confirmed_sim` AND body quality is above
  `reid_body_quality_floor` → resolve via body
- Else if BLE proximity data is available → resolve via BLE
- Else → unresolved (new or unknown person)

**Why rule-based, not a learned fusion model:**
A learned fusion classifier (logistic regression or XGBoost on top of face sim, body sim, BLE
proximity) would be strictly more powerful — but requires labelled training data from the actual
deployment environment. Without ground-truth "this pair is the same person" / "this pair is
different people" labels from the plant floor, any learned fusion model will overfit to whatever
small dataset you construct.

Rule-based fusion with calibrated thresholds is interpretable, auditable, and provably correct
at the boundaries — the right foundation before introducing learned fusion.

**Planned upgrade path:** Once sufficient labelled footage is collected, replace the rule-based
priority logic in `FusionResolver` with a logistic regression trained on
`[face_sim, body_sim, ble_proximity, face_quality_norm, body_quality_norm]`. This would be a
targeted spec change requiring `/advisor` review.

---

### 4.2 The Kalman Spatial Gate

**The problem it solves:** Without a spatial gate, a person leaving Camera A and appearing on
Camera B 30 minutes later at a physically impossible location would be merged into the same
identity (if their body embedding matched). This is a false merge.

**How it works:** Given the known floor-plan topology (which cameras share a physical boundary
and what the approximate transit time is), the Kalman predictor asks: "given where this person
was last seen, could they physically be at this new detection location in this time?" If the
predicted position is incompatible with the new detection, the cross-camera merge is rejected.

**Why Kalman and not a simple distance threshold:**
A distance threshold requires knowing where the camera fields of view physically overlap — static
geometry. A Kalman filter additionally accounts for the dynamic state: how fast was the person
moving, what direction, and does the new detection fit within the uncertainty ellipse of that
trajectory? It is more principled and handles cases where transit time is variable.

---

### 4.3 FAISS as Cache, PostgreSQL as Truth

**The invariant:** PostgreSQL `person_embeddings` is authoritative. FAISS is rebuilt from it on
startup and kept in sync via `faiss_dirty` Redis stream events.

**Why this matters:** FAISS is an in-memory index with no persistence guarantees. If the
process crashes after a FAISS write but before the DB write, the identity is lost. Writing to
the DB first (and committing) before updating FAISS means the worst case is a stale FAISS
index, not lost data. On next startup, FAISS is rebuilt from the DB and consistency is restored.

**The dedup guard at enrollment:** Before adding a new embedding to `person_embeddings`,
cosine similarity is checked against all existing embeddings for that person. If the new
embedding is too similar to an existing one, it is rejected (no information gain) and the
gallery is not inflated. An inflated gallery degrades FAISS search performance and makes
threshold calibration less meaningful.

---

## Part 5: What Was Deliberately NOT Done and Why

---

### 5.1 We Did Not Train Any Model from Scratch

**Decision:** Use pre-trained SOTA models throughout.

**Why:** Training a face recognition model from scratch requires millions of labelled identity
images (WebFace12M has 12 million). Training a Re-ID model requires tens of thousands of
labelled multi-camera person images. The pre-trained models (AdaFace, TransReID) were trained
by research groups over months on this exact data. Fine-tuning them on plant-floor data is a
future option; replacing them with from-scratch CNNs is not.

The resume's "trained a CNN achieving 96% mAP" on aerospace object detection is reasonable
because aerospace has a specific, narrow object domain (aircraft parts, runways) where
general pre-training may not apply. Face recognition and person Re-ID are general enough that
universal pre-training is the correct approach.

---

### 5.2 We Did Not Use a Stacked Ensemble for Core Re-ID

**Decision:** Single ONNX model per task, not XGBoost/RF/SVM ensembles.

**Why:** Stacked ensembles are powerful on tabular structured data (clinical measurements,
financial features, sensor readings). Re-ID is a metric learning problem in a 512-dimensional
embedding space — a domain where:
1. The neural network already learns its own internal ensemble of features
2. Combining XGBoost and SVM predictions on raw pixel or embedding data requires hand-crafted
   features that lose the spatial relationships the CNN was designed to preserve
3. The resulting system would be slower, harder to maintain, and lower accuracy than the single
   end-to-end model

The fusion layer (face + body + BLE) is effectively an ensemble at the identity level — the
"stacked ensemble" idea is implemented there, at the correct abstraction level.

---

### 5.3 We Did Not Apply RFE (Feature Selection) to Embeddings

**Decision:** Embeddings are used at full dimensionality (512-dim).

**Why:** RFE assumes features are independently informative. In a 512-dimensional AdaFace
embedding, the dimensions are entangled — they were jointly trained to produce a specific
cosine geometry. Removing any subset of dimensions distorts the cosine space in unpredictable
ways. PCA-based dimensionality reduction exists for embeddings but would require:
- Fitting PCA on a representative sample of plant-floor embeddings
- Re-indexing the entire FAISS gallery
- Re-calibrating all cosine similarity thresholds
- With no guaranteed accuracy improvement

512-dim FAISS search at scale is fast (sub-millisecond for millions of embeddings). There is
no compute problem to solve by reducing dimensionality.

---

### 5.4 We Did Not Use INT8 Quantisation (Yet)

**Decision:** FP16 for current deployment; INT8 deferred to Phase 6d.

**Why:** INT8 quantisation requires a calibration dataset that covers the full expected input
distribution. Poor calibration degrades accuracy on edge cases — exactly the cases (unusual
lighting, partial occlusion) that matter most for plant-floor surveillance. FP16 is mathematically
near-exact and requires no calibration dataset. The accuracy cost of FP16 vs FP32 is < 0.5% on
ONNX models and < 0.01 cosine drift on embeddings (verified by `trt_fp16_drift_check.py`).

INT8 becomes relevant only at 52+ cameras where CPU decode becomes the bottleneck (≥10ms/frame
after motion gate savings). At the current 12-camera MVP scale, FP16 is sufficient.

---

### 5.5 We Did Not Use SMOTE for Anomaly Detectors

**Decision:** Rule-based anomaly detectors with configurable thresholds; SMOTE only applicable
if/when anomaly detectors are fine-tuned on plant-floor data.

**Why now:** The anomaly detectors (loitering, intrusion, violence) are currently rule-based
or use pre-trained action recognition models. SMOTE applies during model training — specifically
to oversample minority classes. Since no fine-tuning is being done on plant-floor data yet,
SMOTE is not applicable. When fine-tuning does happen (if it does), class imbalance handling
(SMOTE or class-weighted loss) will be mandatory.

---

### 5.6 We Did Not Use Bayesian Threshold Optimisation (Yet)

**Decision:** Manual thresholds, calibrated on webcam footage; Bayesian optimisation is the
planned path for plant-floor calibration.

**Why not yet:** Bayesian hyperparameter optimisation requires a labelled validation set from
the target environment. The system has not yet run in the plant-floor environment with ground-
truth identity labels. The current thresholds are conservative defaults derived from webcam
footage and academic benchmark operating points. The plan is: collect plant-floor footage →
label identity ground truth → run Optuna search over `(adaface_min_sim, reid_body_confirmed_sim,
reid_body_cross_cam_sim)` → update thresholds via `/advisor` review → commit.

---

### 5.7 We Did Not Use DeepStream

**Decision:** ONNX Runtime + TensorRT EP; DeepStream explicitly evaluated and deferred.

**Why:** NVIDIA DeepStream is a full GStreamer-based pipeline toolkit for video analytics.
The evaluation (documented in the GPU spec) found:
1. DeepStream requires reimplementing the entire pipeline in GStreamer plugin architecture —
   a complete rewrite of ingestion, inference, and tracking
2. DeepStream does not support arbitrary Python business logic in the hot path (identity FSM,
   Kalman gating, alert FSM) — these would need to be moved to C++ plugins
3. The performance gain of DeepStream over TRT+Triton narrows to ~10–15% at the scale being
   targeted, which does not justify the rewrite cost
4. NVDEC hardware decode (DeepStream's main advantage) can be accessed directly via PyNvVideoCodec
   if CPU decode ever becomes a bottleneck (Phase 6d)

---

## Part 6: Metrics and What They Mean in Context

---

### 6.1 What "96% mAP" Means in Practice

A 96% mAP on a detection model is a benchmark number on a fixed test set. In production, the
relevant metrics are:
- **False positive rate at the operating threshold** — how many non-face regions does the
  detector fire on?
- **Miss rate at the operating threshold** — how many real faces does the detector miss?
- **Scale generalisation** — does performance hold for small faces (distant camera, crowded scene)?

SCRFD-10G achieves 90.3% AP on WIDER FACE Hard (the subset with small, occluded, dense faces)
which is the relevant operational benchmark for plant-floor surveillance. The 96% mAP number
from the resume is on a specific aerospace dataset — different domain, different meaning.

### 6.2 What "93% Accuracy / 92.5% AUC" Means for Medical ML

For a binary classifier on a balanced medical dataset, 93% accuracy and 92.5% AUC are
reasonable results. AUC is the right metric here because the optimal threshold is a clinical
decision (how much false positive you'll tolerate for how much sensitivity).

In a surveillance Re-ID context, the equivalent is:
- TAR @ FAR=1e-4 (True Accept Rate at a False Accept Rate of 1 in 10,000) — the operating point
  that matters when a false accept means misidentifying a person
- SCRFD: evaluated on WIDER FACE AP
- AdaFace: TAR @ FAR=1e-4 = 97.72% on IJB-C

### 6.3 Our Accuracy Gaps vs Resume Accuracy

The resume reports impressive numbers on controlled benchmark datasets with labelled ground truth.
The current VMS accuracy gaps are operational, not architectural:
1. `adaface_min_sim` is uncalibrated for the deployed IR101 model — known, tracked, requires
   real footage
2. Body Re-ID thresholds calibrated on webcam footage, not plant cameras — known, tracked
3. Cross-camera Kalman gate topology not yet validated on real multi-camera installation —
   requires hardware session

None of these gaps are addressable by switching model architectures. They require calibration
data from the actual deployment environment.

---

## Part 7: Quick Reference — Why This, Not That

| Claim / Technique | Our Position |
|---|---|
| "96% mAP with custom CNN" | SCRFD-10G: 90.3% AP on WIDER FACE Hard (harder benchmark). Custom CNN would perform worse with available data. |
| "Transfer learning on 6,000 fingerprint images" | We use models trained on 12M+ face images / 126K+ Re-ID images. Transfer learning is implicit in using pre-trained ONNX models. |
| "Bayesian hyperparameter optimisation" | Planned for threshold calibration on plant-floor footage. Not yet run because ground-truth labels don't exist yet. |
| "Stacked ensemble (XGBoost + RF + SVM)" | Identity fusion (Face + Body + BLE) is our ensemble. Deep embeddings + cosine search strictly outperforms feature-engineered ensembles on vision tasks. |
| "SMOTE for class imbalance" | Applicable to anomaly detector fine-tuning. Not yet done because no fine-tuning has been run. |
| "RFE feature selection" | Not applicable to 512-dim entangled embeddings. Would distort cosine space and require full gallery re-indexing. |
| "30% compute reduction via quantisation/pruning" | FP16 TRT: 27× speedup at 5-cam. INT8 deferred — no compute problem to solve at current scale. |
| "200ms end-to-end latency" | VMS target: ≤50ms per frame at 52 cameras. 4× more demanding. |
| "15+ FPS on memory-constrained hardware" | VMS runs on a dedicated GPU server (RTX 2000 Ada). Targeting 25+ FPS per camera. |

---

*Last updated: 2026-07-02. Maintained alongside CLAUDE.md — update whenever a model or
architectural decision changes.*
