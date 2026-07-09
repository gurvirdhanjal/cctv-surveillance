"""NVDEC decode-parity integration tests (Phase 6d Task 7).

Run on the GPU workstation only: they need a CUDA GPU plus an FFmpeg build with
cuvid decoders (local install: tools/ffmpeg/bin). Test clips are generated at
test time — no binaries in the repo.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import cv2
import numpy as np
import pytest

from vms.config import Settings
from vms.ingestion import decoder as decoder_module
from vms.ingestion.decoder import NvdecDecoder, OpenCvDecoder, create_decoder

_LOCAL_FFMPEG = Path("tools/ffmpeg/bin/ffmpeg.exe")
_LOCAL_FFPROBE = Path("tools/ffmpeg/bin/ffprobe.exe")
_W, _H, _FPS, _DURATION = 1280, 720, 15, 4
_EXPECTED_FRAMES = _FPS * _DURATION
# cuvid NV12->BGR vs swscale differ by a few LSBs per pixel
_PARITY_MAD = 3.0
_RESIZE_MAD = 12.0  # different scalers (NVDEC vs cv2.INTER_LINEAR)


def _ffmpeg_path() -> str | None:
    if _LOCAL_FFMPEG.exists():
        return str(_LOCAL_FFMPEG)
    import shutil

    return shutil.which("ffmpeg")


def _gpu_present() -> bool:
    from vms.inference.gpu_profile import detect_gpu_profile

    profile = detect_gpu_profile()
    return profile is not None and profile.nvdec_units >= 1


_FFMPEG = _ffmpeg_path()
_SKIP_REASON = "requires CUDA GPU + cuvid-enabled ffmpeg (tools/ffmpeg/bin)"

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(_FFMPEG is None or not _gpu_present(), reason=_SKIP_REASON),
]


@pytest.fixture(autouse=True)
def _nvdec_settings() -> Iterator[None]:
    """Point the decoder module at the local cuvid build; fresh caches per test."""
    assert _FFMPEG is not None
    ffprobe = str(_LOCAL_FFPROBE) if _LOCAL_FFPROBE.exists() else "ffprobe"
    settings = Settings(  # type: ignore[call-arg]
        gpu_nvdec_enabled=True,
        nvdec_ffmpeg_path=_FFMPEG,
        nvdec_ffprobe_path=ffprobe,
    )
    decoder_module.nvdec_available.cache_clear()
    decoder_module.get_session_ledger.cache_clear()
    with patch("vms.ingestion.decoder.get_settings", return_value=settings):
        yield
    decoder_module.nvdec_available.cache_clear()
    decoder_module.get_session_ledger.cache_clear()


def _encode_clip(path: Path, encoder: str) -> bool:
    assert _FFMPEG is not None
    result = subprocess.run(
        [
            _FFMPEG,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={_W}x{_H}:rate={_FPS}:duration={_DURATION}",
            "-c:v",
            encoder,
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        capture_output=True,
        timeout=120,
    )
    return result.returncode == 0 and path.exists()


@pytest.fixture(scope="module")
def h264_clip(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("nvdec") / "ref_h264.mp4"
    assert _encode_clip(path, "libx264"), "test-clip encode failed"
    return path


def _drain(decoder: Any, limit: int = _EXPECTED_FRAMES + 10) -> list[np.ndarray]:
    frames: list[np.ndarray] = []
    for _ in range(limit):
        ret, frame = decoder.read()
        if not ret:
            break
        assert frame is not None
        frames.append(np.array(frame, copy=True))
    return frames


def test_h264_decode_parity_with_opencv(h264_clip: Path) -> None:
    nv = NvdecDecoder(str(h264_clip), "h264", _W, _H)
    nv_frames = _drain(nv)
    nv.release()

    cv = OpenCvDecoder(str(h264_clip))
    cv_frames = _drain(cv)
    cv.release()

    assert len(nv_frames) == len(cv_frames) == _EXPECTED_FRAMES
    assert nv_frames[0].shape == (_H, _W, 3)
    for idx in (0, _EXPECTED_FRAMES // 2, _EXPECTED_FRAMES - 1):
        mad = float(
            np.mean(np.abs(nv_frames[idx].astype(np.int16) - cv_frames[idx].astype(np.int16)))
        )
        assert mad < _PARITY_MAD, f"frame {idx} mean abs diff {mad:.2f} exceeds {_PARITY_MAD}"


def test_hevc_decode_parity_with_opencv(tmp_path: Path) -> None:
    clip = tmp_path / "ref_hevc.mp4"
    if not _encode_clip(clip, "libx265"):
        pytest.skip("libx265 encoder not available in this ffmpeg build")

    nv = NvdecDecoder(str(clip), "hevc", _W, _H)
    nv_frames = _drain(nv)
    nv.release()

    cv = OpenCvDecoder(str(clip))
    cv_frames = _drain(cv)
    cv.release()

    assert len(nv_frames) == len(cv_frames) == _EXPECTED_FRAMES
    mad = float(np.mean(np.abs(nv_frames[0].astype(np.int16) - cv_frames[0].astype(np.int16))))
    assert mad < _PARITY_MAD


def test_nvdec_resize_delivers_presized_frames(h264_clip: Path) -> None:
    half_w, half_h = _W // 2, _H // 2
    nv = NvdecDecoder(str(h264_clip), "h264", half_w, half_h)
    nv_frames = _drain(nv)
    nv.release()

    assert len(nv_frames) == _EXPECTED_FRAMES
    assert nv_frames[0].shape == (half_h, half_w, 3)

    cv = OpenCvDecoder(str(h264_clip))
    ret, full = cv.read()
    cv.release()
    assert ret and full is not None
    reference = cv2.resize(full, (half_w, half_h))
    mad = float(np.mean(np.abs(nv_frames[0].astype(np.int16) - reference.astype(np.int16))))
    assert mad < _RESIZE_MAD


def test_ladder_end_to_end_and_lifecycle_no_zombies(h264_clip: Path) -> None:
    import psutil

    me = psutil.Process()
    before = {p.pid for p in me.children(recursive=True) if "ffmpeg" in p.name().lower()}

    decoders = [
        create_decoder(str(h264_clip), camera_id=100 + i, width=_W, height=_H) for i in range(4)
    ]
    try:
        # full ladder: enabled + available + ffprobe codec probe -> NVDEC path
        assert all(isinstance(d, NvdecDecoder) for d in decoders)
        assert decoder_module.get_session_ledger().active == 4
        for d in decoders:
            ret, frame = d.read()
            assert ret and frame is not None and frame.shape == (_H, _W, 3)
    finally:
        for d in decoders:
            d.release()

    assert decoder_module.get_session_ledger().active == 0
    after = {p.pid for p in me.children(recursive=True) if "ffmpeg" in p.name().lower()}
    assert after - before == set(), "leaked ffmpeg child processes"
