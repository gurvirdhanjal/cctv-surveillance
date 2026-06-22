"""ORT provider helper — TRT EP is gated on gpu_tensorrt_enabled (§6.1)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from vms.config import get_settings
from vms.inference.ort_providers import build_ort_providers


def test_default_returns_cuda_cpu_only(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("VMS_GPU_TENSORRT_ENABLED", "false")
    get_settings.cache_clear()

    providers = build_ort_providers()

    assert providers == ["CUDAExecutionProvider", "CPUExecutionProvider"]
    get_settings.cache_clear()


def test_trt_enabled_puts_trt_ep_first(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    cache = str(tmp_path / "trt_cache")
    monkeypatch.setenv("VMS_GPU_TENSORRT_ENABLED", "true")
    monkeypatch.setenv("VMS_GPU_TENSORRT_ENGINE_CACHE_DIR", cache)
    monkeypatch.setenv("VMS_GPU_TENSORRT_FP16", "true")
    get_settings.cache_clear()

    providers = build_ort_providers()

    assert len(providers) == 3
    first_name, first_opts = providers[0]
    assert first_name == "TensorrtExecutionProvider"
    assert first_opts["trt_fp16_enable"] is True
    assert first_opts["trt_engine_cache_enable"] is True
    assert providers[1] == "CUDAExecutionProvider"
    assert providers[2] == "CPUExecutionProvider"
    get_settings.cache_clear()


def test_trt_creates_cache_dir(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    cache = str(tmp_path / "engines")
    monkeypatch.setenv("VMS_GPU_TENSORRT_ENABLED", "true")
    monkeypatch.setenv("VMS_GPU_TENSORRT_ENGINE_CACHE_DIR", cache)
    get_settings.cache_clear()

    assert not os.path.exists(cache)
    build_ort_providers()
    assert os.path.exists(cache)
    get_settings.cache_clear()


def test_trt_fp16_false_propagates(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("VMS_GPU_TENSORRT_ENABLED", "true")
    monkeypatch.setenv("VMS_GPU_TENSORRT_FP16", "false")
    monkeypatch.setenv("VMS_GPU_TENSORRT_ENGINE_CACHE_DIR", str(tmp_path))
    get_settings.cache_clear()

    providers = build_ort_providers()
    _, trt_opts = providers[0]

    assert trt_opts["trt_fp16_enable"] is False
    get_settings.cache_clear()


def test_workspace_mb_converts_to_bytes(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("VMS_GPU_TENSORRT_ENABLED", "true")
    monkeypatch.setenv("VMS_GPU_TENSORRT_WORKSPACE_MB", "2048")
    monkeypatch.setenv("VMS_GPU_TENSORRT_ENGINE_CACHE_DIR", str(tmp_path))
    get_settings.cache_clear()

    providers = build_ort_providers()
    _, trt_opts = providers[0]

    assert trt_opts["trt_max_workspace_size"] == 2048 * 1024 * 1024
    get_settings.cache_clear()


def test_ppe_model_trt_warmup_runs_on_enabled(monkeypatch, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """PPEModel._load() must call sess.run with a dummy tensor when TRT is enabled."""
    monkeypatch.setenv("VMS_GPU_TENSORRT_ENABLED", "true")
    monkeypatch.setenv("VMS_GPU_TENSORRT_ENGINE_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("VMS_DB_URL", "postgresql://x/y")
    monkeypatch.setenv("VMS_JWT_SECRET", "s")
    get_settings.cache_clear()

    mock_sess = MagicMock()
    mock_sess.get_inputs.return_value = [MagicMock(name="images")]
    mock_ort = MagicMock()
    mock_ort.InferenceSession.return_value = mock_sess

    dummy_model = str(tmp_path / "ppe.onnx")
    open(dummy_model, "w").close()  # empty file — load is mocked

    with patch.dict("sys.modules", {"onnxruntime": mock_ort}):
        from vms.inference import ppe as ppe_mod

        model = ppe_mod.PPEModel.__new__(ppe_mod.PPEModel)
        model._path = dummy_model
        model._session = None
        model._input_name = "images"
        model._conf_threshold = 0.25
        model._nms_iou_threshold = 0.45
        model._target = {}
        model._load(dummy_model)

    mock_sess.run.assert_called_once()
    args = mock_sess.run.call_args
    import numpy as np

    inp = next(iter(args[0][1].values()))
    assert inp.shape == (1, 3, 640, 640)
    assert inp.dtype == np.float32
    get_settings.cache_clear()
