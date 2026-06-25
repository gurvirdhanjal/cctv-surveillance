"""Build Triton Inference Server model repository from local ONNX files.

Operator-run once per deployment (or whenever max_batch_size changes).
Output directory contains one subdirectory per model:

    triton_repo/
      scrfd/     config.pbtxt   1/model.onnx
      adaface/   config.pbtxt   1/model.onnx
      transreid/ config.pbtxt   1/model.onnx
      ppe/       config.pbtxt   1/model.onnx

IO tensor names and shapes are inferred by Triton's auto-complete from the ONNX graph
(--strict-model-config=false at runtime). The config only sets batching behaviour and
instance group; no IO spec is written, which avoids drift when model shapes change.

Dynamic-batch detection: if the leading dimension of the first input is a named
(symbolic) dim in the ONNX graph, max_batch_size is set to the requested value and
dynamic_batching is enabled. If the leading dim is a fixed integer (e.g. YOLO-style
[1,3,640,640]), max_batch_size is forced to 0 (no batching) so Triton does not
misinterpret the fixed batch as a dynamic axis.

Usage:
    python scripts/build_triton_repo.py --src models/ --out models/triton_repo/
    python scripts/build_triton_repo.py --src models/ --out models/triton_repo/ --max-batch 16
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import NamedTuple

import onnx


class _ModelSpec(NamedTuple):
    model_dir: str
    onnx_filename: str


_MODEL_SPECS: list[_ModelSpec] = [
    _ModelSpec(model_dir="scrfd", onnx_filename="scrfd_10g_bnkps.onnx"),
    _ModelSpec(model_dir="adaface", onnx_filename="adaface_ir101_webface12m.onnx"),
    _ModelSpec(model_dir="transreid", onnx_filename="transreid_body_msmt17.onnx"),
    _ModelSpec(model_dir="ppe", onnx_filename="sh17_ppe_yolov8l.onnx"),
]


def _has_dynamic_batch(onnx_path: Path) -> bool:
    """Return True when the model's first input has a symbolic (dynamic) leading dim."""
    graph = onnx.load(str(onnx_path)).graph
    if not graph.input:
        return False
    dim0 = graph.input[0].type.tensor_type.shape.dim[0]
    return dim0.HasField("dim_param")


def _build_config_pbtxt(
    model_name: str,
    onnx_path: Path,
    max_batch_size: int,
) -> str:
    """Emit a minimal config.pbtxt; Triton auto-completes IO from the ONNX graph.

    IO blocks are intentionally omitted so the config never drifts from the ONNX.
    Triton's --strict-model-config=false (required at runtime) handles IO inference.
    max_batch_size is forced to 0 for models with a fixed leading input dimension.
    """
    dynamic = _has_dynamic_batch(onnx_path)
    effective_batch = max_batch_size if dynamic else 0

    lines: list[str] = [
        f'name: "{model_name}"',
        'platform: "onnxruntime_onnx"',
        f"max_batch_size: {effective_batch}",
        "",
    ]

    if effective_batch > 0:
        lines += [
            "dynamic_batching {",
            "  max_queue_delay_microseconds: 1000",
            "}",
            "",
        ]

    lines += [
        "instance_group [ { count: 1 kind: KIND_GPU } ]",
        "",
    ]

    return "\n".join(lines)


def build_repo(
    src_dir: Path,
    out_dir: Path,
    max_batch_size: int = 8,
) -> None:
    """Generate the Triton model repository at out_dir from ONNX files in src_dir.

    Args:
        src_dir: Directory containing the ONNX model files (e.g. models/).
        out_dir: Output directory for the Triton repo (e.g. models/triton_repo/).
        max_batch_size: Dynamic-batch window size for models with dynamic batch input.
                        Fixed-batch models (e.g. YOLO-style) get max_batch_size=0.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    for spec in _MODEL_SPECS:
        onnx_src = src_dir / spec.onnx_filename
        if not onnx_src.exists():
            raise FileNotFoundError(
                f"ONNX model not found: {onnx_src}\n"
                "Run 'vms-models download' to fetch all models first."
            )

        model_out = out_dir / spec.model_dir
        versioned = model_out / "1"
        versioned.mkdir(parents=True, exist_ok=True)

        config = _build_config_pbtxt(spec.model_dir, onnx_src, max_batch_size)
        (model_out / "config.pbtxt").write_text(config, encoding="utf-8")

        shutil.copy2(onnx_src, versioned / "model.onnx")

        dynamic = _has_dynamic_batch(onnx_src)
        effective = max_batch_size if dynamic else 0
        print(f"  {spec.model_dir}: max_batch_size={effective} ({'dynamic' if dynamic else 'fixed'})")

    print(f"Triton repo written to {out_dir} ({len(_MODEL_SPECS)} models)")


def _main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=Path("models"), help="Source ONNX dir")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("models/triton_repo"),
        help="Output Triton repo dir",
    )
    parser.add_argument("--max-batch", type=int, default=8, dest="max_batch_size")
    args = parser.parse_args()
    build_repo(args.src, args.out, args.max_batch_size)


if __name__ == "__main__":
    _main()
