"""Build Triton Inference Server model repository from local ONNX files.

Operator-run once per deployment (or whenever max_batch_size changes).
Output directory contains one subdirectory per model:

    triton_repo/
      scrfd/     config.pbtxt   1/model.onnx
      adaface/   config.pbtxt   1/model.onnx
      transreid/ config.pbtxt   1/model.onnx
      ppe/       config.pbtxt   1/model.onnx

IO tensor names are read from the ONNX graph itself so the config never drifts
from the model. The leading batch dimension is omitted from dims — Triton prepends
it from max_batch_size.

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

_DTYPE_MAP: dict[int, str] = {
    1: "FP32",
    10: "FP16",
    7: "INT64",
    6: "INT32",
    2: "UINT8",
    9: "BOOL",
}


def _onnx_dtype_to_triton(elem_type: int) -> str:
    return _DTYPE_MAP.get(elem_type, "FP32")


def _dim_value(dim: onnx.TensorShapeProto.Dimension) -> int | str:
    """Return the dim as an int or -1 for dynamic dims."""
    if dim.HasField("dim_param"):
        return -1
    return dim.dim_value if dim.dim_value > 0 else -1


def _dims_str(shape_proto: onnx.TensorShapeProto) -> str:
    """Convert ONNX shape (minus the leading batch dim) to a Triton dims list string."""
    dims = [_dim_value(d) for d in shape_proto.dim]
    # Drop the leading (batch) dimension — Triton adds it from max_batch_size.
    dims = dims[1:]
    return ", ".join(str(d) for d in dims)


def _build_config_pbtxt(
    model_name: str,
    onnx_path: Path,
    max_batch_size: int,
) -> str:
    """Read IO names/shapes from the ONNX graph and emit a config.pbtxt string."""
    graph = onnx.load(str(onnx_path)).graph

    input_blocks = []
    for inp in graph.input:
        dtype = _onnx_dtype_to_triton(inp.type.tensor_type.elem_type)
        dims = _dims_str(inp.type.tensor_type.shape)
        input_blocks.append(
            f'  {{\n    name: "{inp.name}"\n    data_type: TYPE_{dtype}\n    dims: [ {dims} ]\n  }}'
        )

    output_blocks = []
    for out in graph.output:
        dtype = _onnx_dtype_to_triton(out.type.tensor_type.elem_type)
        dims = _dims_str(out.type.tensor_type.shape)
        output_blocks.append(
            f'  {{\n    name: "{out.name}"\n    data_type: TYPE_{dtype}\n    dims: [ {dims} ]\n  }}'
        )

    inputs_str = "\n".join(input_blocks)
    outputs_str = "\n".join(output_blocks)

    return (
        f'name: "{model_name}"\n'
        f'platform: "onnxruntime_onnx"\n'
        f"max_batch_size: {max_batch_size}\n"
        f"\n"
        f"input [\n{inputs_str}\n]\n"
        f"\n"
        f"output [\n{outputs_str}\n]\n"
        f"\n"
        f"dynamic_batching {{\n"
        f"  max_queue_delay_microseconds: 1000\n"
        f"}}\n"
        f"\n"
        f"instance_group [ {{ count: 1 kind: KIND_GPU }} ]\n"
    )


def build_repo(
    src_dir: Path,
    out_dir: Path,
    max_batch_size: int = 8,
) -> None:
    """Generate the Triton model repository at out_dir from ONNX files in src_dir.

    Args:
        src_dir: Directory containing the ONNX model files (e.g. models/).
        out_dir: Output directory for the Triton repo (e.g. models/triton_repo/).
        max_batch_size: Dynamic-batch window size written into every config.pbtxt.
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
