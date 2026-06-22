"""Tests for vms.inference.gpu_profile."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from vms.inference.gpu_profile import detect_gpu_profile

# Ensure torch.cuda is importable (it may be lazy on some PyTorch installs).
# patch.object(torch.cuda, ...) requires the submodule to be loaded first.
try:
    import torch
    import torch.cuda as _torch_cuda  # noqa: F401 — loaded for patch.object to work

    _TORCH_AVAILABLE = True
except ImportError:
    _TORCH_AVAILABLE = False


@pytest.fixture(autouse=True)
def clear_lru_cache() -> None:  # type: ignore[return]
    detect_gpu_profile.cache_clear()
    yield
    detect_gpu_profile.cache_clear()


def _make_props(major: int, minor: int, total_memory: int = 16 * 1024**3) -> MagicMock:
    props = MagicMock()
    props.major = major
    props.minor = minor
    props.total_memory = total_memory
    props.name = f"NVIDIA Test GPU {major}.{minor}"
    return props


def test_detect_gpu_profile_import_error_returns_none() -> None:
    """When torch itself is not importable, detect_gpu_profile returns None."""
    with patch.dict("sys.modules", {"torch": None}):
        detect_gpu_profile.cache_clear()
        result = detect_gpu_profile()
    assert result is None


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_detect_gpu_profile_no_cuda_returns_none() -> None:
    with patch.object(torch.cuda, "is_available", return_value=False):
        result = detect_gpu_profile()
    assert result is None


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_gpu_profile_ada_arch() -> None:
    with (
        patch.object(torch.cuda, "is_available", return_value=True),
        patch.object(torch.cuda, "get_device_properties", return_value=_make_props(8, 9)),
    ):
        profile = detect_gpu_profile()
    assert profile is not None
    assert profile.arch == "Ada"
    assert profile.compute_cap == pytest.approx(8.9)


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_gpu_profile_ampere_arch() -> None:
    with (
        patch.object(torch.cuda, "is_available", return_value=True),
        patch.object(torch.cuda, "get_device_properties", return_value=_make_props(8, 6)),
    ):
        profile = detect_gpu_profile()
    assert profile is not None
    assert profile.arch == "Ampere"


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_gpu_profile_turing_arch() -> None:
    with (
        patch.object(torch.cuda, "is_available", return_value=True),
        patch.object(torch.cuda, "get_device_properties", return_value=_make_props(7, 5)),
    ):
        profile = detect_gpu_profile()
    assert profile is not None
    assert profile.arch == "Turing"
    assert profile.supports_int8 is True


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_gpu_profile_volta_no_int8() -> None:
    with (
        patch.object(torch.cuda, "is_available", return_value=True),
        patch.object(torch.cuda, "get_device_properties", return_value=_make_props(7, 0)),
    ):
        profile = detect_gpu_profile()
    assert profile is not None
    assert profile.arch == "Volta"
    assert profile.supports_fp16 is True
    assert profile.supports_int8 is False


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_gpu_profile_fp16_from_volta_onwards() -> None:
    for major, minor in [(7, 0), (7, 5), (8, 0), (8, 9)]:
        detect_gpu_profile.cache_clear()
        with (
            patch.object(torch.cuda, "is_available", return_value=True),
            patch.object(
                torch.cuda, "get_device_properties", return_value=_make_props(major, minor)
            ),
        ):
            profile = detect_gpu_profile()
        assert profile is not None
        assert profile.supports_fp16 is True, f"expected fp16 for {major}.{minor}"


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_gpu_profile_vram_rounded() -> None:
    with (
        patch.object(torch.cuda, "is_available", return_value=True),
        patch.object(
            torch.cuda,
            "get_device_properties",
            return_value=_make_props(8, 9, total_memory=16 * 1024**3),
        ),
    ):
        profile = detect_gpu_profile()
    assert profile is not None
    assert profile.vram_gb == pytest.approx(16.0)


@pytest.mark.skipif(not _TORCH_AVAILABLE, reason="torch not installed")
def test_gpu_profile_is_frozen() -> None:
    with (
        patch.object(torch.cuda, "is_available", return_value=True),
        patch.object(torch.cuda, "get_device_properties", return_value=_make_props(8, 9)),
    ):
        profile = detect_gpu_profile()
    assert profile is not None
    with pytest.raises((AttributeError, TypeError)):
        profile.arch = "modified"  # type: ignore[misc]
