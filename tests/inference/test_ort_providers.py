"""ORT provider helper — TRT EP is gated on gpu_tensorrt_enabled (§6.1)."""

from __future__ import annotations

import os

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
