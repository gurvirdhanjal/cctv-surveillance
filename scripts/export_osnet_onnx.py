"""Download pretrained OSNet x1.0 (Market-1501) and export to ONNX.

OSNet is a person Re-ID model trained on body appearance — angle-invariant,
works from top-down CCTV views. Rank-1 accuracy 94.2% on Market-1501.

Usage:
    pip install torchreid torch onnx
    python scripts/export_osnet_onnx.py

Output: models/osnet_x1_0_market1501.onnx  (~5MB)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
OUT_PATH = REPO_ROOT / "models" / "osnet_x1_0_market1501.onnx"


def main() -> None:
    try:
        import torch
        import torchreid
    except ImportError:
        print("ERROR: install dependencies first:")
        print("  pip install torchreid torch onnx")
        sys.exit(1)

    print("Loading OSNet x1.0 pretrained on Market-1501...")
    model = torchreid.models.build_model(
        name="osnet_x1_0",
        num_classes=751,   # Market-1501 has 751 training identities
        pretrained=True,   # downloads ~21MB .pth from torchreid CDN
    )
    model.eval()

    dummy = torch.zeros(1, 3, 256, 128)  # (B, C, H, W) — portrait crop

    print(f"Exporting to {OUT_PATH} ...")
    OUT_PATH.parent.mkdir(exist_ok=True)
    torch.onnx.export(
        model,
        dummy,
        str(OUT_PATH),
        opset_version=12,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
    )

    size_mb = OUT_PATH.stat().st_size / 1_048_576
    print(f"Done: {OUT_PATH}  ({size_mb:.1f} MB)")
    print()

    # Quick sanity check
    import onnxruntime as ort  # type: ignore[import-untyped]
    import numpy as np
    sess = ort.InferenceSession(str(OUT_PATH), providers=["CPUExecutionProvider"])
    inp = np.zeros((1, 3, 256, 128), dtype=np.float32)
    out = sess.run(None, {"input": inp})[0]
    print(f"Sanity check: input {inp.shape} -> output {out.shape}")
    assert out.shape == (1, 512), f"expected (1,512), got {out.shape}"
    print("OK — 512-dim output confirmed.")


if __name__ == "__main__":
    main()
