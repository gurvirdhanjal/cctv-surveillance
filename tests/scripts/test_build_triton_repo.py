"""Tests for scripts/build_triton_repo.py — Triton model-repo generator (Phase 6c Task 2)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import onnx
import onnx.helper
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).parent.parent.parent / "scripts"


def _import_build_triton_repo():  # type: ignore[return]
    """Import scripts/build_triton_repo.py as a module (not in the package tree)."""
    script_path = _SCRIPTS_DIR / "build_triton_repo.py"
    spec = importlib.util.spec_from_file_location("build_triton_repo", script_path)
    if spec is None or spec.loader is None:
        pytest.skip("build_triton_repo.py not found — run after implementation")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def _make_stub_onnx(
    tmp_path: Path,
    filename: str,
    *,
    input_name: str = "input",
    output_names: list[str] | None = None,
    dynamic_batch: bool = False,
) -> Path:
    """Write a minimal single-input ONNX graph to tmp_path/filename and return its path.

    Args:
        dynamic_batch: when True the leading dim is symbolic ("N"); when False it is
                       fixed at 1. This controls whether build_triton_repo.py detects
                       the model as dynamic-batch or fixed-batch.
    """
    if output_names is None:
        output_names = ["output"]

    fp32 = onnx.TensorProto.FLOAT  # type: ignore[attr-defined]

    if dynamic_batch:
        # Symbolic batch dim — Triton can batch across requests
        batch_dim = onnx.helper.make_tensor_value_info(
            input_name, fp32, ["N", 3, 64, 64]
        )
    else:
        # Fixed batch=1 — must be served with max_batch_size=0
        batch_dim = onnx.helper.make_tensor_value_info(
            input_name, fp32, [1, 3, 64, 64]
        )

    outputs = [onnx.helper.make_tensor_value_info(name, fp32, [1, 10]) for name in output_names]
    node = onnx.helper.make_node("Identity", inputs=[input_name], outputs=[output_names[0]])
    graph = onnx.helper.make_graph([node], "stub", [batch_dim], [outputs[0]])
    model = onnx.helper.make_model(graph, opset_imports=[onnx.helper.make_opsetid("", 17)])
    onnx.checker.check_model(model)
    out_path = tmp_path / filename
    onnx.save(model, str(out_path))
    return out_path


# ONNX file names the script looks for (match _MODEL_SPECS inside the script).
_ONNX_FILENAMES = [
    "scrfd_10g_bnkps.onnx",
    "adaface_ir101_webface12m.onnx",
    "transreid_body_msmt17.onnx",
    "sh17_ppe_yolov8l.onnx",
]

# Expected model directory names — must match what build_triton_repo.py creates.
_EXPECTED_MODEL_DIRS = ["scrfd", "adaface", "transreid", "ppe"]


@pytest.fixture()
def stub_models_dir(tmp_path: pytest.TempPathFactory) -> Path:
    """A models/ directory with one fixed-batch stub ONNX per expected model."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    for fname in _ONNX_FILENAMES:
        _make_stub_onnx(models_dir, fname, dynamic_batch=False)
    return models_dir


@pytest.fixture()
def dynamic_models_dir(tmp_path: pytest.TempPathFactory) -> Path:
    """A models/ directory with one dynamic-batch stub ONNX per expected model."""
    models_dir = tmp_path / "models_dynamic"
    models_dir.mkdir()
    for fname in _ONNX_FILENAMES:
        _make_stub_onnx(models_dir, fname, dynamic_batch=True)
    return models_dir


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_triton_repo_creates_four_model_dirs(stub_models_dir: Path, tmp_path: Path) -> None:
    """build_repo() must create one directory per model, each with config.pbtxt + 1/model.onnx."""
    mod = _import_build_triton_repo()
    out_dir = tmp_path / "triton_repo"

    mod.build_repo(stub_models_dir, out_dir)

    for model_name in _EXPECTED_MODEL_DIRS:
        model_dir = out_dir / model_name
        assert model_dir.is_dir(), f"Missing model dir: {model_name}"
        assert (model_dir / "config.pbtxt").is_file(), f"Missing config.pbtxt for {model_name}"
        assert (model_dir / "1" / "model.onnx").is_file(), f"Missing 1/model.onnx for {model_name}"


def test_build_triton_repo_config_omits_io_blocks_for_triton_autocomplete(
    stub_models_dir: Path, tmp_path: Path
) -> None:
    """config.pbtxt must NOT contain input/output blocks — IO is delegated to Triton auto-complete.

    The script dropped explicit IO spec (Phase 6c fix) so Triton reads tensor names and
    shapes directly from the ONNX graph via --disable-auto-complete-config=false.
    Writing IO blocks caused protobuf parse errors for multi-output models and shape
    mismatches when output dims were symbolic.
    """
    mod = _import_build_triton_repo()
    out_dir = tmp_path / "triton_repo_noio"

    mod.build_repo(stub_models_dir, out_dir)

    for model_name in _EXPECTED_MODEL_DIRS:
        config_text = (out_dir / model_name / "config.pbtxt").read_text()
        assert "input [" not in config_text, (
            f"{model_name}/config.pbtxt contains explicit 'input [' block — "
            "IO spec must be omitted so Triton auto-completes from the ONNX graph."
        )
        assert "output [" not in config_text, (
            f"{model_name}/config.pbtxt contains explicit 'output [' block — "
            "IO spec must be omitted so Triton auto-completes from the ONNX graph."
        )


def test_build_triton_repo_fixed_batch_sets_max_batch_zero(
    stub_models_dir: Path, tmp_path: Path
) -> None:
    """Fixed-batch models (leading dim=1) must get max_batch_size: 0 and no dynamic_batching."""
    mod = _import_build_triton_repo()
    out_dir = tmp_path / "triton_repo_fixed"

    mod.build_repo(stub_models_dir, out_dir, max_batch_size=8)

    for model_name in _EXPECTED_MODEL_DIRS:
        config_text = (out_dir / model_name / "config.pbtxt").read_text()
        assert "max_batch_size: 0" in config_text, (
            f"{model_name}: expected max_batch_size: 0 for fixed-batch model"
        )
        assert "dynamic_batching" not in config_text, (
            f"{model_name}: dynamic_batching must not appear for fixed-batch model"
        )


def test_build_triton_repo_dynamic_batch_uses_requested_max_batch(
    dynamic_models_dir: Path, tmp_path: Path
) -> None:
    """Dynamic-batch models (symbolic leading dim) use the requested max_batch_size."""
    mod = _import_build_triton_repo()
    out_dir = tmp_path / "triton_repo_dyn"

    mod.build_repo(dynamic_models_dir, out_dir, max_batch_size=16)

    for model_name in _EXPECTED_MODEL_DIRS:
        config_text = (out_dir / model_name / "config.pbtxt").read_text()
        assert "max_batch_size: 16" in config_text, (
            f"{model_name}: expected max_batch_size: 16 for dynamic-batch model"
        )
        assert "dynamic_batching" in config_text, (
            f"{model_name}: dynamic_batching block missing for dynamic-batch model"
        )
        assert "max_queue_delay_microseconds: 1000" in config_text, (
            f"{model_name}: max_queue_delay_microseconds: 1000 missing"
        )


def test_build_triton_repo_config_specifies_onnxruntime_platform(
    stub_models_dir: Path, tmp_path: Path
) -> None:
    """config.pbtxt must set platform to onnxruntime_onnx (not TensorRT or default)."""
    mod = _import_build_triton_repo()
    out_dir = tmp_path / "triton_repo_plat"

    mod.build_repo(stub_models_dir, out_dir)

    for model_name in _EXPECTED_MODEL_DIRS:
        config_text = (out_dir / model_name / "config.pbtxt").read_text()
        assert (
            "onnxruntime_onnx" in config_text
        ), f"Missing platform onnxruntime_onnx in {model_name}/config.pbtxt"
