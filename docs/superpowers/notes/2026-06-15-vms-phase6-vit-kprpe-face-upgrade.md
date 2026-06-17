# Phase 6: ViT-KPRPE Face Recognition Upgrade (Deferred)

**Status: DEFERRED — do not implement without GPU acceleration spec landed (Phase 6)**

---

## What this is

AdaFace ViT-KPRPE is the highest-scoring face recognition model on TinyFace (surveillance benchmark):

| Model | TinyFace R1 | TinyFace R5 | IJB-C@0.01 |
|---|---|---|---|
| IR101/WebFace12M (Phase 5 target) | 72.42 | 74.81 | 97.72 |
| **ViT-KPRPE/WebFace4M** | **75.75** | **78.49** | 97.13 |
| **ViT-KPRPE/WebFace12M** | **76.10** | **78.92** | 97.82 |

HuggingFace repos:
- `minchul/cvlface_adaface_vit_base_kprpe_webface4m`
- `minchul/cvlface_adaface_vit_base_kprpe_webface12m`

Paper: KP-RPE — KeyPoint Relative Position Encoding for Face Recognition (CVPR 2024, arXiv 2403.14852)

---

## Why deferred

### 1. Non-standard model interface

ViT-KPRPE takes **two inputs** — not a drop-in ONNX swap:
- Input 1: `(1, 3, 112, 112)` face crop (same as IR101)
- Input 2: `(1, 5, 2)` keypoint tensor — 5-point facial landmarks in 112×112 aligned space

We have SCRFD keypoints available (from `scrfd_10g_bnkps.onnx`), but `AdaFaceEmbedder.embed()` signature, the ONNX export, and the inference call all need changing. Not a one-file change.

### 2. ViT inference cost at 52 cameras

ViT-B/16 at ~100M params vs IR101 at 65M params. Without TensorRT FP16, per-frame latency will exceed the 50ms budget at 52 cameras. Needs the GPU acceleration spec (`2026-06-13-vms-gpu-acceleration.md`) landed first.

### 3. ONNX export is non-trivial

KPRPE uses position biases derived from the keypoint input inside the attention layers. Standard `torch.onnx.export` may not handle this cleanly — requires tracing with both inputs simultaneously and verifying the exported graph handles dynamic keypoint values correctly.

---

## Pre-conditions before implementing

- [ ] GPU acceleration spec Phase 6 complete (TensorRT FP16, ONNX Runtime TensorRT EP)
- [ ] Benchmark IR101/WebFace12M on real plant footage first — if gap is <3pp, ViT-KPRPE may not be worth the complexity
- [ ] ONNX export script verified: two-input export, traced with real keypoints, output diff < 1e-4 vs PyTorch
- [ ] `AdaFaceEmbedder` interface extended: `embed(face, frame_bgr, keypoints)` — keypoints passed through from detector
- [ ] Re-calibrate `adaface_min_sim` after switch (mandatory `/advisor` per CLAUDE.md §0.5)
- [ ] Load test: measure p99 frame latency at 52 cameras with ViT-KPRPE vs IR101

---

## Implementation sketch (for when pre-conditions are met)

```python
# ONNX export (one-time)
from transformers import AutoModel
import torch

model = AutoModel.from_pretrained(
    "minchul/cvlface_adaface_vit_base_kprpe_webface12m",
    trust_remote_code=True,
)
model.eval()

dummy_face = torch.randn(1, 3, 112, 112)
dummy_kps  = torch.zeros(1, 5, 2)  # keypoints in 112×112 aligned-crop space

torch.onnx.export(
    model.net,
    (dummy_face, dummy_kps),
    "models/adaface_vit_kprpe_webface12m.onnx",
    input_names=["face", "keypoints"],
    output_names=["embedding"],
    dynamic_axes={"face": {0: "batch"}, "keypoints": {0: "batch"}},
    opset_version=17,
)
```

Embedder change needed:
```python
# vms/inference/embedder.py — new signature when KPRPE is active
def embed(self, face: FaceWithEmbedding, frame_bgr, keypoints_112=None):
    ...
    if keypoints_112 is not None:
        raw = self._sess.run(None, {
            self._input_name: blob,
            "keypoints": keypoints_112,
        })
    else:
        raw = self._sess.run(None, {self._input_name: blob})
```

Keypoints must be transformed from original frame space → 112×112 aligned-crop space using the same affine matrix `M` computed in `_align_face()`.

---

## Recorded: 2026-06-15
