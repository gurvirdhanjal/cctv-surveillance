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
) -> Path:
    """Write a minimal single-input ONNX graph to tmp_path/filename and return its path."""
    if output_names is None:
        output_names = ["output"]

    fp32 = onnx.TensorProto.FLOAT  # type: ignore[attr-defined]
    inputs = [onnx.helper.make_tensor_value_info(input_name, fp32, [1, 3, 64, 64])]
    outputs = [onnx.helper.make_tensor_value_info(name, fp32, [1, 10]) for name in output_names]
    # Use the first output for the Identity node; remaining outputs are constants for simplicity.
    node = onnx.helper.make_node("Identity", inputs=[input_name], outputs=[output_names[0]])
    graph = onnx.helper.make_graph([node], "stub", inputs, [outputs[0]])
    model = onnx.helper.make_model(graph, opset_imports=[onnx.helper.make_opsetid("", 17)])
    onnx.checker.check_model(model)
    out_path = tmp_path / filename
    onnx.save(model, str(out_path))
    return out_path


# Expected model directory names — must match what build_triton_repo.py creates.
_EXPECTED_MODEL_DIRS = ["scrfd", "adaface", "transreid", "ppe"]

# ONNX file names the script looks for (match _MODEL_SPECS inside the script).
_ONNX_FILENAMES = [
    "scrfd_10g_bnkps.onnx",
    "adaface_ir101_webface12m.onnx",
    "transreid_body_msmt17.onnx",
    "sh17_ppe_yolov8l.onnx",
]


@pytest.fixture()
def stub_models_dir(tmp_path: pytest.TempPathFactory) -> Path:
    """A directory that looks like models/ with one stub ONNX per expected model."""
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    for fname in _ONNX_FILENAMES:
        _make_stub_onnx(models_dir, fname)
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


def test_build_triton_repo_config_uses_onnx_graph_io_names(tmp_path: Path) -> None:
    """config.pbtxt must reference the actual ONNX graph IO names, not hard-coded strings."""
    mod = _import_build_triton_repo()

    # Build a models dir with a scrfd stub that has custom IO names.
    models_dir = tmp_path / "models_custom"
    models_dir.mkdir()
    custom_input = "my_custom_input_xyz"
    custom_output = "my_custom_output_xyz"
    # Put the stub under the expected scrfd filename.
    _make_stub_onnx(
        models_dir,
        "scrfd_10g_bnkps.onnx",
        input_name=custom_input,
        output_names=[custom_output],
    )
    # Remaining models use default names (script must handle them too).
    for fname in _ONNX_FILENAMES[1:]:
        _make_stub_onnx(models_dir, fname)

    out_dir = tmp_path / "triton_repo_custom"
    mod.build_repo(models_dir, out_dir)

    config_text = (out_dir / "scrfd" / "config.pbtxt").read_text()
    assert custom_input in config_text, (
        f"Expected custom input name {custom_input!r} in config.pbtxt — "
        "script must read IO names from the ONNX graph, not hard-code them."
    )
    assert custom_output in config_text, (
        f"Expected custom output name {custom_output!r} in config.pbtxt — "
        "script must read IO names from the ONNX graph, not hard-code them."
    )


def test_build_triton_repo_config_contains_dynamic_batching_block(
    stub_models_dir: Path, tmp_path: Path
) -> None:
    """Every config.pbtxt must contain the dynamic_batching block with 1ms queue delay."""
    mod = _import_build_triton_repo()
    out_dir = tmp_path / "triton_repo_dyn"

    mod.build_repo(stub_models_dir, out_dir)

    for model_name in _EXPECTED_MODEL_DIRS:
        config_text = (out_dir / model_name / "config.pbtxt").read_text()
        assert (
            "dynamic_batching" in config_text
        ), f"Missing dynamic_batching block in {model_name}/config.pbtxt"
        assert (
            "max_queue_delay_microseconds: 1000" in config_text
        ), f"Missing max_queue_delay_microseconds: 1000 in {model_name}/config.pbtxt"


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


def test_build_triton_repo_custom_max_batch_size(stub_models_dir: Path, tmp_path: Path) -> None:
    """max_batch_size passed to build_repo must appear in every config.pbtxt."""
    mod = _import_build_triton_repo()
    out_dir = tmp_path / "triton_repo_bs"

    mod.build_repo(stub_models_dir, out_dir, max_batch_size=16)

    for model_name in _EXPECTED_MODEL_DIRS:
        config_text = (out_dir / model_name / "config.pbtxt").read_text()
        assert (
            "max_batch_size: 16" in config_text
        ), f"Expected max_batch_size: 16 in {model_name}/config.pbtxt"
