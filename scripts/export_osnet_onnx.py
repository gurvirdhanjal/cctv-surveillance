"""Export OSNet AIN x1.0 MSMT17 weights to ONNX for Triton inference.

Input:  (N, 3, 256, 128) FP32 — portrait crop, ImageNet normalised.
Output: (N, 512) FP32 — L2-normalised body Re-ID embedding.

Exports with a dynamic batch axis so Triton's dynamic batching can merge
requests from multiple cameras into one kernel launch.

Usage:
    python scripts/download_osnet_ain_msmt17.py      # fetch weights first
    python scripts/export_osnet_onnx.py              # export + validate
    python scripts/export_osnet_onnx.py --out models/custom.onnx

Exit code 1 on cosine drift >= 0.9999 gate failure (identity correctness,
CLAUDE.md priority #2).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent.parent
DEFAULT_WEIGHTS = REPO_ROOT / "models" / "osnet_ain_x1_0_msmt17.pth"
DEFAULT_OUT = REPO_ROOT / "models" / "osnet_ain_x1_0_msmt17.onnx"
OPSET = 17  # matches onnxruntime >= 1.18 used in Triton ORT backend
_COSINE_THRESHOLD = 0.9999


def cosine_passes(
    a: np.ndarray[..., np.dtype[np.float32]],
    b: np.ndarray[..., np.dtype[np.float32]],
    threshold: float = _COSINE_THRESHOLD,
) -> bool:
    """Return True if cosine similarity between a and b >= threshold."""
    a_norm = a / np.linalg.norm(a)
    b_norm = b / np.linalg.norm(b)
    return float(np.dot(a_norm.ravel(), b_norm.ravel())) >= threshold


def export_and_validate(
    weights_path: str = str(DEFAULT_WEIGHTS),
    out_path: str = str(DEFAULT_OUT),
) -> float:
    """Export model to ONNX and return cosine similarity (torch vs onnxruntime).

    Raises RuntimeError if cosine < 0.9999.
    """
    try:
        import torch
        import torchreid
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError(
            f"Missing dependency: {exc}. " "pip install torch torchreid onnxruntime"
        ) from exc

    weights_p = Path(weights_path)
    if not weights_p.exists():
        raise FileNotFoundError(
            f"Weights not found: {weights_p}. " "Run: python scripts/download_osnet_ain_msmt17.py"
        )

    print(f"Loading osnet_ain_x1_0 from {weights_p} ...")
    model = torchreid.models.build_model(
        name="osnet_ain_x1_0",
        num_classes=1041,  # MSMT17 has 1041 training identities
        pretrained=False,
    )
    state = torch.load(str(weights_p), map_location="cpu", weights_only=True)
    # torchreid checkpoints wrap state in {"state_dict": ...} or are bare state_dicts
    sd = state.get("state_dict", state)
    model.load_state_dict(sd, strict=True)
    model.eval()

    dummy = torch.randn(1, 3, 256, 128, dtype=torch.float32)

    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    print(f"Exporting to {out_p} (opset {OPSET}) ...")
    with torch.no_grad():
        torch.onnx.export(
            model,
            dummy,
            str(out_p),
            opset_version=OPSET,
            input_names=["input"],
            output_names=["output"],
            dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
        )

    size_mb = out_p.stat().st_size / 1_048_576
    print(f"Exported: {out_p}  ({size_mb:.1f} MB)")

    # Identity-correctness gate: cosine(torch_emb, ort_emb) >= 0.9999
    with torch.no_grad():
        torch_out = model(dummy).numpy()[0]

    sess = ort.InferenceSession(str(out_p), providers=["CPUExecutionProvider"])
    ort_out = sess.run(None, {"input": dummy.numpy()})[0][0]

    cosine = float(np.dot(torch_out / np.linalg.norm(torch_out), ort_out / np.linalg.norm(ort_out)))
    print(f"Cosine (torch vs ort): {cosine:.7f}")

    if not cosine_passes(torch_out, ort_out):
        raise RuntimeError(
            f"Cosine {cosine:.7f} < {_COSINE_THRESHOLD} — embedding drift detected. "
            "STOP: mandatory /advisor before proceeding (CLAUDE.md §0.5)."
        )

    print(f"Identity gate PASSED (cosine={cosine:.7f} >= {_COSINE_THRESHOLD})")
    return cosine


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="Path to .pth weights")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output .onnx path")
    args = parser.parse_args()

    try:
        cosine = export_and_validate(weights_path=args.weights, out_path=args.out)
        print(f"\nDone. cosine={cosine:.7f}")
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
