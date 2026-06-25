"""Tests for scripts/export_osnet_onnx.py (Phase 6c Task 7).

Unit-tests: cosine_passes helper — no torch/onnx needed.
Integration test: full export + shape check, gated behind @pytest.mark.integration
and skipped when the .pth weights are absent.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"
_WEIGHTS_PATH = Path(__file__).parent.parent.parent / "models" / "osnet_ain_x1_0_msmt17.pth"


def _import_export_osnet():  # type: ignore[return]
    script_path = _SCRIPTS_DIR / "export_osnet_onnx.py"
    spec = importlib.util.spec_from_file_location("export_osnet_onnx", script_path)
    if spec is None or spec.loader is None:
        pytest.skip("export_osnet_onnx.py not found")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# Unit tests — cosine_passes helper (no GPU/torch required)
# ---------------------------------------------------------------------------


def test_export_osnet_validation_helper_passes_identical_vectors() -> None:
    """cosine_passes returns True for identical embeddings (cosine = 1.0)."""
    mod = _import_export_osnet()
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    assert mod.cosine_passes(a, a.copy()) is True


def test_export_osnet_validation_helper_flags_drift() -> None:
    """cosine_passes returns False when cosine < 0.9999."""
    mod = _import_export_osnet()
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0, 0.0], dtype=np.float32)  # orthogonal — cosine = 0.0
    assert mod.cosine_passes(a, b) is False


def test_export_osnet_validation_helper_near_threshold() -> None:
    """cosine_passes uses strict >= 0.9999 threshold."""
    mod = _import_export_osnet()
    # construct a vector with cosine just below 0.9999
    a = np.array([1.0, 0.0], dtype=np.float32)
    angle = np.arccos(0.9998)  # cosine 0.9998 < 0.9999 -> fail
    b = np.array([np.cos(angle), np.sin(angle)], dtype=np.float32)
    assert mod.cosine_passes(a, b) is False

    angle2 = np.arccos(0.99995)  # cosine 0.99995 >= 0.9999 -> pass
    c = np.array([np.cos(angle2), np.sin(angle2)], dtype=np.float32)
    assert mod.cosine_passes(a, c) is True


# ---------------------------------------------------------------------------
# Integration test — export + IO shape check (skipped without weights or torch)
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_export_osnet_onnx_io_shapes(tmp_path: Path) -> None:
    """Export script produces an ONNX with (N,3,256,128) input and (N,512) output."""
    if not _WEIGHTS_PATH.exists():
        pytest.skip(
            f"Weights not present: {_WEIGHTS_PATH}. Run download_osnet_ain_msmt17.py first."
        )
    try:
        import onnx  # noqa: F401
        import torch  # noqa: F401
        import torchreid  # noqa: F401
    except ImportError:
        pytest.skip("torch/torchreid/onnx not installed — integration test requires full env")

    mod = _import_export_osnet()
    out_path = tmp_path / "osnet_ain_x1_0_msmt17.onnx"
    cosine = mod.export_and_validate(weights_path=str(_WEIGHTS_PATH), out_path=str(out_path))

    assert out_path.exists(), "Export script did not produce an ONNX file"
    assert cosine >= 0.9999, f"Cosine {cosine:.6f} < 0.9999 — embedding drift detected"

    import onnx as onnx_mod

    graph = onnx_mod.load(str(out_path))
    inputs = graph.graph.input
    outputs = graph.graph.output
    # dynamic batch axis: shape[0] is a dim_param (string), not a fixed int
    in_shape = [d.dim_value for d in inputs[0].type.tensor_type.shape.dim]
    out_shape = [d.dim_value for d in outputs[0].type.tensor_type.shape.dim]
    # dynamic dim is 0 (dim_value=0 for symbolic dims in protobuf)
    assert in_shape[1] == 3
    assert in_shape[2] == 256
    assert in_shape[3] == 128
    assert out_shape[1] == 512
