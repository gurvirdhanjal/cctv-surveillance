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

    cache_dir = settings.gpu_tensorrt_engine_cache_dir
    os.makedirs(cache_dir, exist_ok=True)

    trt_opts: dict[str, Any] = {
        "trt_engine_cache_enable": True,
        "trt_engine_cache_path": cache_dir,
        "trt_fp16_enable": settings.gpu_tensorrt_fp16,
        "trt_max_workspace_size": settings.gpu_tensorrt_workspace_mb * 1024 * 1024,
    }
    logger.info(
        "TensorRT EP enabled (fp16=%s, cache=%s, workspace=%d MB)",
        settings.gpu_tensorrt_fp16,
        cache_dir,
        settings.gpu_tensorrt_workspace_mb,
    )
    return [
        ("TensorrtExecutionProvider", trt_opts),
        "CUDAExecutionProvider",
        "CPUExecutionProvider",
    ]
