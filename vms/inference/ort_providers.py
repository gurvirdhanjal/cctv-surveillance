"""ORT provider list builder — shared by all ONNX models (§6.1).

When VMS_GPU_TENSORRT_ENABLED=true:  [TensorrtExecutionProvider, CUDA, CPU]
When disabled (default):             [CUDAExecutionProvider, CPUExecutionProvider]

The TRT engine cache dir is created here so each model loader does not need to.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def build_ort_providers() -> list[Any]:
    """Return the ORT provider list for all VMS ONNX models."""
    from vms.config import get_settings  # lazy — avoids circular import at module level

    settings = get_settings()

    if not settings.gpu_tensorrt_enabled:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]

    # Gate FP16 on actual GPU capability — don't force it on hardware that doesn't benefit.
    from vms.inference.gpu_profile import detect_gpu_profile

    profile = detect_gpu_profile()
    fp16_enabled = settings.gpu_tensorrt_fp16
    if fp16_enabled and profile is not None and not profile.supports_fp16:
        fp16_enabled = False
        logger.warning(
            "GPU arch %s (cap %.1f) does not support FP16 — TRT FP16 disabled",
            profile.arch,
            profile.compute_cap,
        )

    cache_dir = settings.gpu_tensorrt_engine_cache_dir
    os.makedirs(cache_dir, exist_ok=True)

    trt_opts: dict[str, Any] = {
        "trt_engine_cache_enable": True,
        "trt_engine_cache_path": cache_dir,
        "trt_fp16_enable": fp16_enabled,
        "trt_max_workspace_size": settings.gpu_tensorrt_workspace_mb * 1024 * 1024,
    }
    logger.info(
        "TensorRT EP enabled (fp16=%s, arch=%s, cache=%s, workspace=%d MB)",
        fp16_enabled,
        profile.arch if profile else "unknown",
        cache_dir,
        settings.gpu_tensorrt_workspace_mb,
    )
    return [
        ("TensorrtExecutionProvider", trt_opts),
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ]
