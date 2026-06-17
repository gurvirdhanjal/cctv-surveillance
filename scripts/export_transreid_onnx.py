"""Export ViT-B16+ICS_MSMT17.pth to ONNX for body Re-ID inference.

Input checkpoint:  models/ViT-B16+ICS_MSMT17.pth  (343 MB, supervised TransReID-SSL)
Output ONNX:       models/transreid_body_msmt17.onnx (~343 MB)

After export, set VMS_TRANSREID_BODY_MODEL=models/transreid_body_msmt17.onnx and
swap the BodyEmbedder in the engine for TransReIDBodyEmbedder.

Architecture (reconstructed from checkpoint key analysis, 2026-06-15):

  ICS conv stem:
    Conv2d(3→64, 7×7, stride=2, pad=3, bias=False)
    IBN(64)  [InstanceNorm on ch 0:32, BatchNorm on ch 32:64]
    ReLU
    Conv2d(64→64, 3×3, stride=1, pad=1, bias=False)
    IBN(64)
    ReLU
    Conv2d(64→64, 3×3, stride=1, pad=1, bias=False)
    BatchNorm2d(64)
    ReLU
    Conv2d(64→768, 8×8, stride=8)           ← patch projection

  ViT-B/16 transformer: depth=12, hidden=768, heads=12, mlp_ratio=4.0
  BNNeck: BatchNorm1d(768)
  Output:  L2-normalised 768-dim embedding

  Input resolution: 384×128 (H×W).
    After stride-2 stem → 192×64.
    After stride-8 proj → 24×8 = 192 tokens + 1 CLS = pos_embed[1,193,768]. ✓

Usage:
    python scripts/export_transreid_onnx.py
    python scripts/export_transreid_onnx.py --input models/ViT-B16+ICS_MSMT17.pth
    python scripts/export_transreid_onnx.py --verify-only models/transreid_body_msmt17.onnx

Build-time dependencies (not needed at inference):
    pip install torch onnx
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_DEFAULT_INPUT = "models/ViT-B16+ICS_MSMT17.pth"
_DEFAULT_OUTPUT = "models/transreid_body_msmt17.onnx"
_INPUT_H = 384
_INPUT_W = 128
_EMBED_DIM = 768
_NUM_PATCHES = 192  # 24×8 grid from 384×128 at effective stride 16
_OPSET = 14


# ---------------------------------------------------------------------------
# Architecture — inline reimplementation matching the checkpoint exactly.
# No external TransReID repo required.
# ---------------------------------------------------------------------------


def _build_model() -> "torch.nn.Module":  # noqa: F821
    import torch
    import torch.nn as nn
    import torch.nn.functional as F

    class _IBN(nn.Module):
        """IBN-Net style norm: InstanceNorm on first half of channels, BN on second half.

        conv.1 and conv.4 in the ICS stem use this pattern.
        Checkpoint keys: conv.N.IN.{weight,bias}, conv.N.BN.{weight,bias,running_*}
        with each half having planes//2 elements.
        """

        def __init__(self, planes: int) -> None:
            super().__init__()
            half = planes // 2
            self.IN = nn.InstanceNorm2d(half, affine=True)
            self.BN = nn.BatchNorm2d(half)
            self._half = half

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            x_in = self.IN(x[:, : self._half].contiguous())
            x_bn = self.BN(x[:, self._half :].contiguous())
            return torch.cat([x_in, x_bn], dim=1)

    class _ICSPatchEmbed(nn.Module):
        """ICS convolutional patch embedding for TransReID-SSL ViT-B/16.

        Sequential indices match checkpoint keys exactly (ReLU has no params):
          conv.0  Conv2d(3,64,7,s=2)
          conv.1  IBN(64)
          conv.2  ReLU  [no params]
          conv.3  Conv2d(64,64,3,s=1)
          conv.4  IBN(64)
          conv.5  ReLU  [no params]
          conv.6  Conv2d(64,64,3,s=1)
          conv.7  BN(64)
          conv.8  ReLU  [no params]
          proj    Conv2d(64,768,8,s=8)
        """

        def __init__(self) -> None:
            super().__init__()
            self.conv = nn.Sequential(
                nn.Conv2d(3, 64, 7, stride=2, padding=3, bias=False),  # 0
                _IBN(64),  # 1
                nn.ReLU(inplace=True),  # 2
                nn.Conv2d(64, 64, 3, stride=1, padding=1, bias=False),  # 3
                _IBN(64),  # 4
                nn.ReLU(inplace=True),  # 5
                nn.Conv2d(64, 64, 3, stride=1, padding=1, bias=False),  # 6
                nn.BatchNorm2d(64),  # 7
                nn.ReLU(inplace=True),  # 8
            )
            self.proj = nn.Conv2d(64, _EMBED_DIM, kernel_size=8, stride=8)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            x = self.conv(x)  # (B, 64, H/2, W/2)
            x = self.proj(x)  # (B, 768, H/16, W/16)
            return x.flatten(2).transpose(1, 2)  # (B, N, 768)

    class _Attention(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.num_heads = 12
            self.head_dim = _EMBED_DIM // 12  # 64
            self.scale = self.head_dim**-0.5
            self.qkv = nn.Linear(_EMBED_DIM, _EMBED_DIM * 3)
            self.proj = nn.Linear(_EMBED_DIM, _EMBED_DIM)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            B, N, C = x.shape
            qkv = self.qkv(x).reshape(B, N, 3, self.num_heads, self.head_dim).permute(2, 0, 3, 1, 4)
            q, k, v = qkv.unbind(0)
            attn = (q @ k.transpose(-2, -1)) * self.scale
            attn = attn.softmax(dim=-1)
            x = (attn @ v).transpose(1, 2).reshape(B, N, C)
            return self.proj(x)

    class _MLP(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.fc1 = nn.Linear(_EMBED_DIM, _EMBED_DIM * 4)
            self.act = nn.GELU()
            self.fc2 = nn.Linear(_EMBED_DIM * 4, _EMBED_DIM)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            return self.fc2(self.act(self.fc1(x)))

    class _Block(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.norm1 = nn.LayerNorm(_EMBED_DIM)
            self.attn = _Attention()
            self.norm2 = nn.LayerNorm(_EMBED_DIM)
            self.mlp = _MLP()

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            x = x + self.attn(self.norm1(x))
            x = x + self.mlp(self.norm2(x))
            return x

    class _ViTBase(nn.Module):
        """ViT-B/16 backbone with ICS stem.

        base.fc (ImageNet head baked into backbone during SSL pretraining) is declared
        so the state dict loads cleanly with strict=False. It is never called at inference.
        """

        def __init__(self) -> None:
            super().__init__()
            self.patch_embed = _ICSPatchEmbed()
            self.cls_token = nn.Parameter(torch.zeros(1, 1, _EMBED_DIM))
            self.pos_embed = nn.Parameter(torch.zeros(1, _NUM_PATCHES + 1, _EMBED_DIM))
            self.blocks = nn.ModuleList([_Block() for _ in range(12)])
            self.norm = nn.LayerNorm(_EMBED_DIM)
            self.fc = nn.Linear(_EMBED_DIM, 1000)  # SSL pretraining head; not used at inference

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            B = x.shape[0]
            tokens = self.patch_embed(x)  # (B, 192, 768)
            cls = self.cls_token.expand(B, -1, -1)  # (B, 1, 768)
            tokens = torch.cat([cls, tokens], dim=1)  # (B, 193, 768)
            tokens = tokens + self.pos_embed
            for block in self.blocks:
                tokens = block(tokens)
            tokens = self.norm(tokens)
            return tokens[:, 0]  # CLS token (B, 768)

    class _TransReIDInference(nn.Module):
        """ViT-B/16+ICS backbone + BNNeck. Outputs L2-normalised 768-dim body embeddings.

        classifier (MSMT17 ID head) is intentionally omitted — not needed at inference.
        Loaded from ViT-B16+ICS_MSMT17.pth with strict=False.
        """

        def __init__(self) -> None:
            super().__init__()
            self.base = _ViTBase()
            self.bottleneck = nn.BatchNorm1d(_EMBED_DIM)

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            feat = self.base(x)  # (B, 768)
            feat_bn = self.bottleneck(feat)  # BNNeck
            return F.normalize(feat_bn, p=2, dim=1)  # L2-normalised (B, 768)

    return _TransReIDInference()


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def _export(input_path: Path, output_path: Path) -> None:
    import torch

    if not input_path.exists():
        sys.exit(f"Checkpoint not found: {input_path}")

    print(f"Loading checkpoint: {input_path}")
    state_dict = torch.load(str(input_path), map_location="cpu", weights_only=False)

    model = _build_model()

    missing, unexpected = model.load_state_dict(state_dict, strict=False)

    # Expected unexpected: classifier.weight, classifier.bias (omitted from inference model)
    # Expected missing: none (all base.* and bottleneck.* should match)
    unexpected_real = [k for k in unexpected if not k.startswith("classifier.")]
    if unexpected_real:
        print(f"WARNING: unexpected keys after stripping classifier: {unexpected_real}")
    if missing:
        print(f"WARNING: missing keys: {missing}")

    model.eval()

    dummy = torch.zeros(1, 3, _INPUT_H, _INPUT_W)
    with torch.no_grad():
        out = model(dummy)
    print(f"PyTorch forward: input {tuple(dummy.shape)} -> output {tuple(out.shape)}")
    assert out.shape == (1, _EMBED_DIM), f"expected (1,{_EMBED_DIM}), got {out.shape}"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Exporting to {output_path} (opset {_OPSET}) ...")

    torch.onnx.export(
        model,
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


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def _verify(output_path: Path) -> None:
    try:
        import numpy as np
        import onnxruntime as ort  # type: ignore[import-untyped]
    except ImportError:
        sys.exit("onnxruntime not installed. Run: pip install onnxruntime")

    import numpy as np

    print(f"Verifying {output_path} ...")
    sess = ort.InferenceSession(str(output_path), providers=["CPUExecutionProvider"])
    input_name = sess.get_inputs()[0].name

    dummy = np.random.randn(1, 3, _INPUT_H, _INPUT_W).astype(np.float32)
    outputs = sess.run(None, {input_name: dummy})
    emb = outputs[0]

    assert emb.shape == (1, _EMBED_DIM), f"bad shape: {emb.shape}"

    norm = float(np.linalg.norm(emb[0]))
    if abs(norm - 1.0) > 0.01:
        print(f"  WARNING: embedding norm={norm:.4f} — not L2-normalised. Check forward pass.")
    else:
        print(f"  Embedding norm: {norm:.6f}  (L2-normalised)")

    # Batch consistency: two identical inputs should give identical outputs
    dummy2 = np.tile(dummy, (2, 1, 1, 1))
    out2 = sess.run(None, {input_name: dummy2})[0]
    assert np.allclose(out2[0], out2[1], atol=1e-5), "Batch outputs diverge — check model"
    print(f"  Shape: {emb.shape}  dtype: {emb.dtype}")
    print("Verification passed.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", default=_DEFAULT_INPUT, help="Input .pth checkpoint")
    parser.add_argument("--output", default=_DEFAULT_OUTPUT, help="Output ONNX path")
    parser.add_argument(
        "--verify-only", metavar="PATH", help="Skip export, only verify existing ONNX"
    )
    args = parser.parse_args()

    if args.verify_only:
        _verify(Path(args.verify_only))
        return

    _export(Path(args.input), Path(args.output))
    _verify(Path(args.output))

    print()
    print("=" * 60)
    print("Next steps:")
    print(f"  1. Set VMS_TRANSREID_BODY_MODEL={args.output}")
    print("  2. Swap BodyEmbedder -> TransReIDBodyEmbedder in the engine")
    print("     (see vms/inference/body_embedder.py — TransReIDBodyEmbedder)")
    print("  3. Re-calibrate reid_body_confirmed_sim on real footage")
    print("     (current 0.51 was calibrated for OSNet/DukeMTMC — not valid for TransReID)")
    print("     MANDATORY /advisor before changing reid_body_confirmed_sim (CLAUDE.md §0.5)")
    print("=" * 60)


if __name__ == "__main__":
    main()
