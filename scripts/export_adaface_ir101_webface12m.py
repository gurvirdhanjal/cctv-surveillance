"""Export AdaFace IR101/WebFace12M from CVLFace HuggingFace to ONNX.

Run once — produces models/adaface_ir101_webface12m.onnx (~262MB, single file).
After export, set VMS_ADAFACE_MODEL=models/adaface_ir101_webface12m.onnx.

What this script does:
  1. Downloads model snapshot from HuggingFace to tmp/cvlface_ir101_snapshot/
     (includes weights, model code, and configs — ~500MB total)
  2. Loads the IResNet101 backbone using the bundled CVLFace model code
  3. Exports to ONNX (opset 14, single file, ~262MB)
  4. Verifies output shape and L2 normalisation with onnxruntime

Build-time dependencies (not needed at inference time):
    pip install torch transformers accelerate omegaconf huggingface_hub

Usage:
    python scripts/export_adaface_ir101_webface12m.py
    python scripts/export_adaface_ir101_webface12m.py --output models/custom_name.onnx
    python scripts/export_adaface_ir101_webface12m.py --verify-only models/adaface_ir101_webface12m.onnx
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_HF_REPO = "minchul/cvlface_adaface_ir101_webface12m"
_SNAPSHOT_DIR = Path("tmp/cvlface_ir101_snapshot")
_DEFAULT_OUT = "models/adaface_ir101_webface12m.onnx"
_INPUT_SIZE = 112
_EMBED_DIM = 512
_OPSET = 14


def _download_snapshot() -> Path:
    """Download HuggingFace snapshot to a local directory (no symlinks)."""
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        sys.exit("huggingface_hub not installed. Run: pip install huggingface_hub")

    # Check if already downloaded (model.pt is the large file)
    model_pt = _SNAPSHOT_DIR / "pretrained_model" / "model.pt"
    if model_pt.exists():
        print(f"Snapshot already at {_SNAPSHOT_DIR} — skipping download.")
        return _SNAPSHOT_DIR.resolve()

    _SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {_HF_REPO} to {_SNAPSHOT_DIR} (this may take several minutes) ...")
    snapshot_download(_HF_REPO, local_dir=str(_SNAPSHOT_DIR))
    print(f"Download complete: {_SNAPSHOT_DIR}")
    return _SNAPSHOT_DIR.resolve()


def _load_backbone(snapshot_dir: Path):  # type: ignore[return]
    """Load the IResNet101 backbone from the snapshot."""
    try:
        import torch
    except ImportError:
        sys.exit("torch not installed. Run: pip install torch")

    # The snapshot bundles its own 'models' package and pretrained_model/ weights.
    # Add snapshot dir to sys.path (absolute) BEFORE changing directory.
    snapshot_abs = str(snapshot_dir)
    if snapshot_abs not in sys.path:
        sys.path.insert(0, snapshot_abs)

    original_cwd = Path.cwd()
    os.chdir(snapshot_dir)

    try:
        from omegaconf import OmegaConf  # type: ignore[import-untyped]
        from models import get_model  # type: ignore[import-untyped]

        config = json.loads(Path("config.json").read_text())
        model_conf = OmegaConf.create(config["conf"])
        print(f"Config: name={model_conf.name}, output_dim={model_conf.output_dim}, "
              f"color_space={model_conf.color_space}")

        model = get_model(model_conf)
        model.load_state_dict_from_path("pretrained_model/model.pt")
        model.eval()
    finally:
        os.chdir(original_cwd)

    # Export model.model (the CVLFace IResNet wrapper) rather than model.net (raw backbone).
    # The wrapper includes L2 normalisation in its forward pass; exporting it means the ONNX
    # graph produces unit-norm embeddings directly — no post-processing needed.
    backbone = getattr(model, "model", model)
    print(f"Backbone: model.model ({type(backbone).__name__})")

    # Verify forward pass before exporting.
    dummy = torch.randn(1, 3, _INPUT_SIZE, _INPUT_SIZE)
    with torch.no_grad():
        out = backbone(dummy)
        if isinstance(out, (tuple, list)):
            out = out[0]
        elif isinstance(out, dict):
            out = list(out.values())[0]
        print(f"PyTorch output shape: {tuple(out.shape)}")
        if tuple(out.shape) != (1, _EMBED_DIM):
            sys.exit(f"Unexpected output shape {tuple(out.shape)} — expected (1, {_EMBED_DIM})")

    return backbone


def _export(output_path: Path) -> None:
    import torch

    snapshot_dir = _download_snapshot()
    backbone = _load_backbone(snapshot_dir)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dummy = torch.randn(1, 3, _INPUT_SIZE, _INPUT_SIZE)

    print(f"Exporting to {output_path} (opset {_OPSET}) ...")
    # dynamo=False uses the legacy TorchScript tracer — stable for IResNet101
    # and avoids torch 2.9 dynamo emoji output that breaks Windows CP1252 terminals.
    torch.onnx.export(
        backbone,
        dummy,
        str(output_path),
        input_names=["input"],
        output_names=["embedding"],
        dynamic_axes={"input": {0: "batch"}, "embedding": {0: "batch"}},
        opset_version=_OPSET,
        do_constant_folding=True,
        dynamo=False,
    )
    size_mb = output_path.stat().st_size / 1e6
    print(f"Exported: {output_path} ({size_mb:.1f} MB)")


def _verify(output_path: Path) -> None:
    try:
        import numpy as np
        import onnxruntime as ort
    except ImportError:
        sys.exit("onnxruntime not installed. Run: pip install onnxruntime")

    import numpy as np

    print(f"Verifying {output_path} ...")
    sess = ort.InferenceSession(str(output_path), providers=["CPUExecutionProvider"])
    input_name = sess.get_inputs()[0].name

    dummy = np.random.randn(1, 3, _INPUT_SIZE, _INPUT_SIZE).astype(np.float32)
    outputs = sess.run(None, {input_name: dummy})
    emb = outputs[0]

    assert emb.shape == (1, _EMBED_DIM), f"Bad shape: {emb.shape}"

    norm = float(np.linalg.norm(emb[0]))
    if abs(norm - 1.0) > 0.01:
        print(f"  WARNING: embedding norm={norm:.4f} — not L2-normalised internally.")
        print("  The embedder will need manual L2 normalisation.")
    else:
        print(f"  Embedding norm: {norm:.6f}  (L2-normalised)")

    print(f"  Shape: {emb.shape}  dtype: {emb.dtype}")
    print("Verification passed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--output", default=_DEFAULT_OUT, help="Output ONNX path")
    parser.add_argument("--verify-only", metavar="PATH", help="Skip export, only verify existing ONNX")
    args = parser.parse_args()

    if args.verify_only:
        _verify(Path(args.verify_only))
    else:
        out = Path(args.output)
        _export(out)
        _verify(out)
        print()
        print("=" * 60)
        print("Next steps:")
        print(f"  1. VMS_ADAFACE_MODEL defaults to {out} (already set in config.py)")
        print("  2. Re-calibrate adaface_min_sim on real footage")
        print("     (mandatory /advisor per CLAUDE.md §0.5 before changing the value)")
        print("     Current default 0.72 was calibrated for IR50/MS1MV2.")
        print("=" * 60)


if __name__ == "__main__":
    main()
