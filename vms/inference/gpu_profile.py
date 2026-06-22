"""GPU hardware probe for arch-gated precision decisions (§6.0).

detect_gpu_profile() is called once at startup (lru_cached) and used by
ort_providers.build_ort_providers() to gate TRT FP16/INT8 on capability.
Returns None when no CUDA GPU is available (CI / dev laptop path).
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GpuProfile:
    arch: str  # "Ada", "Ampere", "Turing", "Volta", "Unknown(X.Y)"
    compute_cap: float  # e.g. 8.9 for Ada Lovelace
    vram_gb: float
    nvdec_units: int  # hardware video decode units (1 for most consumer cards)
    supports_fp16: bool  # True from Volta (7.0) onwards
    supports_int8: bool  # True from Turing (7.5) onwards with good throughput


@functools.lru_cache(maxsize=1)
def detect_gpu_profile() -> GpuProfile | None:
    """Probe the first CUDA GPU via torch. Returns None if CUDA is unavailable."""
    try:
        import torch

        if not torch.cuda.is_available():
            logger.debug("No CUDA GPU detected — TRT acceleration unavailable")
            return None

        props = torch.cuda.get_device_properties(0)
        major: int = props.major
        minor: int = props.minor
        compute_cap = float(f"{major}.{minor}")
        vram_gb = round(props.total_memory / (1024**3), 1)

        if major >= 9:
            arch = "Hopper"
        elif major == 8 and minor == 9:
            arch = "Ada"
        elif major == 8:
            arch = "Ampere"
        elif major == 7 and minor == 5:
            arch = "Turing"
        elif major == 7:
            arch = "Volta"
        else:
            arch = f"Unknown({major}.{minor})"

        # Consumer cards (GeForce, RTX A-series mobile): 1 NVDEC unit.
        # Professional/data-center: 2+. Heuristic — probe via nvdec is optional for §6.3.
        nvdec_units = 1

        supports_fp16 = compute_cap >= 7.0
        supports_int8 = compute_cap >= 7.5

        profile = GpuProfile(
            arch=arch,
            compute_cap=compute_cap,
            vram_gb=vram_gb,
            nvdec_units=nvdec_units,
            supports_fp16=supports_fp16,
            supports_int8=supports_int8,
        )
        logger.info(
            "GPU: %s (arch=%s, cap=%.1f, VRAM=%.1f GB, fp16=%s, int8=%s)",
            props.name,
            arch,
            compute_cap,
            vram_gb,
            supports_fp16,
            supports_int8,
        )
        return profile

    except Exception as exc:
        logger.warning("GPU profile probe failed (%s) — falling back to CUDA EP", exc)
        return None
