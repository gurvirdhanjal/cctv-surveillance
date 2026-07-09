"""Tests for the DecodeBackend protocol + decode probes (Phase 6d Tasks 1-2)."""

from __future__ import annotations

import subprocess
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from vms.ingestion.decoder import (
    DecodeBackend,
    NvdecDecoder,
    OpenCvDecoder,
    _mask_url,
    build_nvdec_command,
    nvdec_available,
    probe_codec,
)
from vms.ingestion.worker import CameraConfig, IngestionWorker

_SECRET_URL = "rtsp://admin:secret123@10.0.0.5:554/Streaming/Channels/101"


@pytest.fixture(autouse=True)
def _clear_probe_caches() -> Any:
    nvdec_available.cache_clear()
    yield
    nvdec_available.cache_clear()


def _gpu_profile(nvdec_units: int = 1) -> Any:
    from vms.inference.gpu_profile import GpuProfile

    return GpuProfile(
        arch="Ada",
        compute_cap=8.9,
        vram_gb=16.0,
        nvdec_units=nvdec_units,
        supports_fp16=True,
        supports_int8=True,
    )


class _FakeDecoder:
    """Minimal structural DecodeBackend used to drive the worker loop."""

    def __init__(self, frames: int, width: int = 64, height: int = 48) -> None:
        self._remaining = frames
        self._shape = (height, width, 3)
        self.released = False

    def read(self) -> tuple[bool, np.ndarray | None]:  # type: ignore[type-arg]
        if self._remaining <= 0:
            return False, None
        self._remaining -= 1
        return True, np.zeros(self._shape, dtype=np.uint8)

    def get_resolution(self) -> tuple[int, int]:
        return self._shape[1], self._shape[0]

    def release(self) -> None:
        self.released = True


def test_fake_and_opencv_decoders_satisfy_protocol() -> None:
    assert isinstance(_FakeDecoder(1), DecodeBackend)
    with patch("vms.ingestion.decoder.cv2.VideoCapture", return_value=MagicMock()):
        assert isinstance(OpenCvDecoder("rtsp://x"), DecodeBackend)


def test_opencv_decoder_limits_rtsp_buffer_to_one_frame() -> None:
    import cv2

    mock_cap = MagicMock()
    with patch("vms.ingestion.decoder.cv2.VideoCapture", return_value=mock_cap):
        OpenCvDecoder("rtsp://x")
    mock_cap.set.assert_called_once_with(cv2.CAP_PROP_BUFFERSIZE, 1)


def test_opencv_decoder_reports_resolution_from_capture() -> None:
    import cv2

    mock_cap = MagicMock()
    mock_cap.get.side_effect = lambda prop: {
        cv2.CAP_PROP_FRAME_WIDTH: 1280.0,
        cv2.CAP_PROP_FRAME_HEIGHT: 720.0,
    }[prop]
    with patch("vms.ingestion.decoder.cv2.VideoCapture", return_value=mock_cap):
        decoder = OpenCvDecoder("rtsp://x")
    assert decoder.get_resolution() == (1280, 720)
    decoder.release()
    mock_cap.release.assert_called_once()


@pytest.mark.asyncio
async def test_worker_uses_injected_decoder_factory() -> None:
    cfg = CameraConfig(camera_id=7, rtsp_url="rtsp://x", worker_group=1, width=64, height=48)
    decoder = _FakeDecoder(frames=1)
    factory_urls: list[str] = []

    def factory(url: str) -> _FakeDecoder:
        factory_urls.append(url)
        return decoder

    published: list[dict[str, str]] = []

    async def capture_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        published.append(fields)
        worker._running = False
        return "1-0"

    worker = IngestionWorker(cfg, AsyncMock(), decoder_factory=factory)

    with (
        patch("vms.ingestion.worker.stream_add", side_effect=capture_stream_add),
        patch("vms.ingestion.worker.SHMSlot.create") as mock_create,
    ):
        mock_slot = MagicMock()
        mock_slot.name = "vms_cam_7"
        mock_slot.write.return_value = 1000
        mock_create.return_value = mock_slot
        await worker.start()

    assert factory_urls == ["rtsp://x"]
    assert len(published) == 1
    assert decoder.released is True


# -- capability probe (Task 2) --------------------------------------------------


def test_nvdec_available_true_when_gpu_and_cuvid_present() -> None:
    run_result = MagicMock(stdout="V..... h264_cuvid  Nvidia CUVID H264 decoder", returncode=0)
    with (
        patch("vms.ingestion.decoder.detect_gpu_profile", return_value=_gpu_profile()),
        patch("vms.ingestion.decoder.subprocess.run", return_value=run_result) as mock_run,
    ):
        assert nvdec_available() is True
        # lru-cached: a second call must not re-run ffmpeg
        assert nvdec_available() is True
    assert mock_run.call_count == 1


def test_nvdec_available_false_without_gpu_skips_ffmpeg() -> None:
    with (
        patch("vms.ingestion.decoder.detect_gpu_profile", return_value=None),
        patch("vms.ingestion.decoder.subprocess.run") as mock_run,
    ):
        assert nvdec_available() is False
    mock_run.assert_not_called()


def test_nvdec_available_false_when_ffmpeg_missing_logs_warning(caplog: Any) -> None:
    with (
        patch("vms.ingestion.decoder.detect_gpu_profile", return_value=_gpu_profile()),
        patch("vms.ingestion.decoder.subprocess.run", side_effect=FileNotFoundError),
        caplog.at_level("WARNING"),
    ):
        assert nvdec_available() is False
    assert any("ffmpeg" in r.getMessage().lower() for r in caplog.records)


def test_nvdec_available_false_when_build_lacks_cuvid() -> None:
    run_result = MagicMock(stdout="V..... h264  plain decoder", returncode=0)
    with (
        patch("vms.ingestion.decoder.detect_gpu_profile", return_value=_gpu_profile()),
        patch("vms.ingestion.decoder.subprocess.run", return_value=run_result),
    ):
        assert nvdec_available() is False


# -- codec probe (Task 2) --------------------------------------------------------


def test_probe_codec_returns_h264_and_hevc() -> None:
    for codec in ("h264", "hevc"):
        run_result = MagicMock(stdout=f"{codec}\n", returncode=0)
        with patch("vms.ingestion.decoder.subprocess.run", return_value=run_result):
            assert probe_codec(_SECRET_URL) == codec


def test_probe_codec_none_on_failure_timeout_or_unknown() -> None:
    fail = MagicMock(stdout="", returncode=1)
    with patch("vms.ingestion.decoder.subprocess.run", return_value=fail):
        assert probe_codec(_SECRET_URL) is None
    with patch(
        "vms.ingestion.decoder.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="ffprobe", timeout=10),
    ):
        assert probe_codec(_SECRET_URL) is None
    unknown = MagicMock(stdout="mjpeg\n", returncode=0)
    with patch("vms.ingestion.decoder.subprocess.run", return_value=unknown):
        assert probe_codec(_SECRET_URL) is None


def test_probe_failures_never_log_credentials(caplog: Any) -> None:
    fail = MagicMock(stdout="", returncode=1)
    with (
        patch("vms.ingestion.decoder.subprocess.run", return_value=fail),
        caplog.at_level("DEBUG"),
    ):
        probe_codec(_SECRET_URL)
    with (
        patch("vms.ingestion.decoder.detect_gpu_profile", return_value=_gpu_profile()),
        patch("vms.ingestion.decoder.subprocess.run", side_effect=FileNotFoundError),
        caplog.at_level("DEBUG"),
    ):
        nvdec_available()
    for record in caplog.records:
        assert "secret123" not in record.getMessage()
        assert "admin:" not in record.getMessage()


def test_mask_url_strips_credentials() -> None:
    assert _mask_url(_SECRET_URL) == "rtsp://***@10.0.0.5:554/Streaming/Channels/101"
    assert _mask_url("rtsp://10.0.0.5/ch1") == "rtsp://10.0.0.5/ch1"
    assert _mask_url("file.mp4") == "file.mp4"


# -- NvdecDecoder (Task 3) -------------------------------------------------------

_W, _H = 8, 4
_FRAME_BYTES = _W * _H * 3


class _FakeProc:
    """Fake ffmpeg subprocess serving scripted bgr24 bytes on stdout."""

    def __init__(self, payload: bytes, stderr: bytes = b"") -> None:
        import io

        self.stdout = io.BytesIO(payload)
        self.stderr = io.BytesIO(stderr)
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        return 0


def _decoder(payloads: list[bytes], **kwargs: Any) -> tuple[NvdecDecoder, list[_FakeProc]]:
    procs: list[_FakeProc] = []

    def factory(*_args: Any, **_kw: Any) -> _FakeProc:
        proc = _FakeProc(payloads[min(len(procs), len(payloads) - 1)])
        procs.append(proc)
        return proc

    decoder = NvdecDecoder("rtsp://x", "h264", _W, _H, popen_factory=factory, **kwargs)
    return decoder, procs


def test_build_nvdec_command_rtsp_h264() -> None:
    cmd = build_nvdec_command(_SECRET_URL, "h264", 1280, 720, ffmpeg_path="tools/ffmpeg.exe")
    assert cmd[0] == "tools/ffmpeg.exe"
    i_pos = cmd.index("-i")
    # decoder + NVDEC-side resize + transport are input options: all BEFORE -i
    assert cmd.index("-c:v") < i_pos and cmd[cmd.index("-c:v") + 1] == "h264_cuvid"
    assert cmd.index("-resize") < i_pos and cmd[cmd.index("-resize") + 1] == "1280x720"
    assert cmd.index("-rtsp_transport") < i_pos and cmd[cmd.index("-rtsp_transport") + 1] == "tcp"
    assert cmd[i_pos + 1] == _SECRET_URL
    assert cmd[-1] == "pipe:1"
    assert "bgr24" in cmd and "rawvideo" in cmd


def test_build_nvdec_command_file_input_hevc_no_rtsp_transport() -> None:
    cmd = build_nvdec_command("clip.mp4", "hevc", 640, 360, ffmpeg_path="ffmpeg")
    assert "-rtsp_transport" not in cmd
    assert cmd[cmd.index("-c:v") + 1] == "hevc_cuvid"


def test_nvdec_read_exact_framing_then_eof() -> None:
    payload = (bytes(range(256)) * ((_FRAME_BYTES * 3 // 256) + 1))[: _FRAME_BYTES * 3]
    decoder, _procs = _decoder([payload])

    for _ in range(3):
        ret, frame = decoder.read()
        assert ret is True
        assert frame is not None and frame.shape == (_H, _W, 3) and frame.dtype == np.uint8
    ret, frame = decoder.read()
    assert ret is False and frame is None
    assert decoder.get_resolution() == (_W, _H)


def test_nvdec_short_read_returns_false() -> None:
    decoder, _ = _decoder([b"\x00" * (_FRAME_BYTES - 5)])
    ret, frame = decoder.read()
    assert ret is False and frame is None


def test_nvdec_restarts_subprocess_after_consecutive_failures() -> None:
    # empty stdout -> every read fails; restart threshold default is 3
    decoder, procs = _decoder([b"", b"\x00" * _FRAME_BYTES])

    assert decoder.read() == (False, None)
    assert decoder.read() == (False, None)
    assert len(procs) == 1
    assert decoder.read() == (False, None)  # 3rd failure -> kill + relaunch
    assert len(procs) == 2
    assert procs[0].terminated is True and procs[0].wait_calls >= 1

    ret, frame = decoder.read()  # relaunched proc serves one good frame
    assert ret is True and frame is not None


def test_nvdec_release_reaps_process_and_fires_callback_once() -> None:
    released: list[int] = []
    decoder, procs = _decoder([b""], on_release=lambda: released.append(1))

    decoder.release()
    decoder.release()  # idempotent

    assert procs[0].terminated is True
    assert procs[0].wait_calls >= 1
    assert released == [1]


def test_nvdec_stderr_drained_at_debug_with_masked_url(caplog: Any) -> None:
    import io

    def factory(*_args: Any, **_kw: Any) -> _FakeProc:
        proc = _FakeProc(b"")
        proc.stderr = io.BytesIO(b"[rtsp] some ffmpeg noise\n")
        return proc

    with caplog.at_level("DEBUG", logger="vms.ingestion.decoder"):
        decoder = NvdecDecoder(_SECRET_URL, "h264", _W, _H, popen_factory=factory)
        assert decoder._stderr_thread is not None
        decoder._stderr_thread.join(timeout=2.0)
        decoder.release()

    noise = [r for r in caplog.records if "ffmpeg noise" in r.getMessage()]
    assert noise and noise[0].levelname == "DEBUG"
    for record in caplog.records:
        assert "secret123" not in record.getMessage()


@pytest.mark.asyncio
async def test_worker_skips_resize_for_correctly_sized_frames() -> None:
    cfg = CameraConfig(camera_id=9, rtsp_url="rtsp://x", worker_group=1, width=64, height=48)
    decoder = _FakeDecoder(frames=1, width=64, height=48)

    async def stop_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        worker._running = False
        return "1-0"

    worker = IngestionWorker(cfg, AsyncMock(), decoder_factory=lambda _url: decoder)

    with (
        patch("vms.ingestion.worker.stream_add", side_effect=stop_stream_add),
        patch("vms.ingestion.worker.SHMSlot.create") as mock_create,
        patch("vms.ingestion.worker.cv2.resize") as mock_resize,
    ):
        mock_slot = MagicMock()
        mock_slot.name = "vms_cam_9"
        mock_slot.write.return_value = 1000
        mock_create.return_value = mock_slot
        await worker.start()

    mock_resize.assert_not_called()


# -- session ledger + fallback ladder (Task 4) -------------------------------------


def test_ledger_caps_and_releases() -> None:
    from vms.ingestion.decoder import NvdecSessionLedger

    ledger = NvdecSessionLedger(max_sessions=2)
    assert ledger.acquire() is True
    assert ledger.acquire() is True
    assert ledger.acquire() is False  # cap reached
    ledger.release()
    assert ledger.acquire() is True
    ledger.release()
    ledger.release()
    ledger.release()  # over-release never goes negative
    assert ledger.active == 0


def test_ledger_thread_safety_never_overallocates() -> None:
    import threading

    from vms.ingestion.decoder import NvdecSessionLedger

    ledger = NvdecSessionLedger(max_sessions=5)
    granted: list[bool] = []
    lock = threading.Lock()

    def worker() -> None:
        got = ledger.acquire()
        with lock:
            granted.append(got)

    threads = [threading.Thread(target=worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(granted) == 5


def _settings(enabled: bool = True, max_sessions: int = 12) -> MagicMock:
    s = MagicMock()
    s.gpu_nvdec_enabled = enabled
    s.nvdec_max_sessions = max_sessions
    s.nvdec_ffmpeg_path = "ffmpeg"
    s.nvdec_restart_after_failures = 3
    return s


@pytest.fixture()
def _fresh_ledger() -> Any:
    from vms.ingestion import decoder as decoder_module

    decoder_module.get_session_ledger.cache_clear()
    yield
    decoder_module.get_session_ledger.cache_clear()


def _make(url: str = "rtsp://x", camera_id: int = 5) -> Any:
    from vms.ingestion.decoder import create_decoder

    return create_decoder(url, camera_id=camera_id, width=64, height=48)


def test_factory_disabled_returns_opencv_without_probing(_fresh_ledger: Any) -> None:
    with (
        patch("vms.ingestion.decoder.get_settings", return_value=_settings(enabled=False)),
        patch("vms.ingestion.decoder.OpenCvDecoder") as mock_cv,
        patch("vms.ingestion.decoder.nvdec_available") as mock_avail,
        patch("vms.ingestion.decoder.probe_codec") as mock_probe,
    ):
        _make()
    mock_cv.assert_called_once_with("rtsp://x")
    mock_avail.assert_not_called()
    mock_probe.assert_not_called()


def test_factory_falls_back_when_nvdec_unavailable(_fresh_ledger: Any, caplog: Any) -> None:
    with (
        patch("vms.ingestion.decoder.get_settings", return_value=_settings()),
        patch("vms.ingestion.decoder.OpenCvDecoder") as mock_cv,
        patch("vms.ingestion.decoder.nvdec_available", return_value=False),
        caplog.at_level("WARNING"),
    ):
        _make()
    mock_cv.assert_called_once()
    assert any("NVDEC" in r.getMessage() for r in caplog.records)


def test_factory_falls_back_when_codec_probe_fails(_fresh_ledger: Any, caplog: Any) -> None:
    with (
        patch("vms.ingestion.decoder.get_settings", return_value=_settings()),
        patch("vms.ingestion.decoder.OpenCvDecoder") as mock_cv,
        patch("vms.ingestion.decoder.nvdec_available", return_value=True),
        patch("vms.ingestion.decoder.probe_codec", return_value=None),
        caplog.at_level("WARNING"),
    ):
        _make(camera_id=42)
    mock_cv.assert_called_once()
    assert any("camera_id=42" in r.getMessage() for r in caplog.records)


def test_factory_falls_back_when_session_cap_reached(_fresh_ledger: Any, caplog: Any) -> None:
    with (
        patch("vms.ingestion.decoder.get_settings", return_value=_settings(max_sessions=0)),
        patch("vms.ingestion.decoder.OpenCvDecoder") as mock_cv,
        patch("vms.ingestion.decoder.nvdec_available", return_value=True),
        patch("vms.ingestion.decoder.probe_codec", return_value="h264"),
        caplog.at_level("WARNING"),
    ):
        _make()
    mock_cv.assert_called_once()
    assert any("session cap" in r.getMessage() for r in caplog.records)


def test_factory_releases_slot_when_nvdec_startup_fails(_fresh_ledger: Any) -> None:
    from vms.ingestion import decoder as decoder_module

    with (
        patch("vms.ingestion.decoder.get_settings", return_value=_settings(max_sessions=1)),
        patch("vms.ingestion.decoder.OpenCvDecoder") as mock_cv,
        patch("vms.ingestion.decoder.nvdec_available", return_value=True),
        patch("vms.ingestion.decoder.probe_codec", return_value="h264"),
        patch("vms.ingestion.decoder.NvdecDecoder", side_effect=OSError("spawn failed")),
    ):
        _make()
        assert decoder_module.get_session_ledger().active == 0  # slot given back
    mock_cv.assert_called_once()


def test_factory_success_wires_ledger_release(_fresh_ledger: Any) -> None:
    from vms.ingestion import decoder as decoder_module

    captured: dict[str, Any] = {}

    def fake_nvdec(url: str, codec: str, width: int, height: int, **kwargs: Any) -> MagicMock:
        captured["codec"] = codec
        captured["on_release"] = kwargs["on_release"]
        return MagicMock(name="nvdec")

    with (
        patch("vms.ingestion.decoder.get_settings", return_value=_settings(max_sessions=1)),
        patch("vms.ingestion.decoder.nvdec_available", return_value=True),
        patch("vms.ingestion.decoder.probe_codec", return_value="hevc"),
        patch("vms.ingestion.decoder.NvdecDecoder", side_effect=fake_nvdec),
    ):
        _make()
        ledger = decoder_module.get_session_ledger()
        assert ledger.active == 1
        captured["on_release"]()  # decoder.release() must free the slot
        assert ledger.active == 0
    assert captured["codec"] == "hevc"


# -- worker + config integration (Task 5) -------------------------------------------


def test_nvdec_settings_env_var_round_trip(monkeypatch: Any) -> None:
    from vms.config import Settings

    monkeypatch.setenv("VMS_NVDEC_FFMPEG_PATH", "tools/ffmpeg/bin/ffmpeg.exe")
    monkeypatch.setenv("VMS_NVDEC_FFPROBE_PATH", "tools/ffmpeg/bin/ffprobe.exe")
    monkeypatch.setenv("VMS_NVDEC_MAX_SESSIONS", "3")
    monkeypatch.setenv("VMS_NVDEC_PROBE_TIMEOUT_S", "7")
    monkeypatch.setenv("VMS_NVDEC_RESTART_AFTER_FAILURES", "5")

    settings = Settings()  # type: ignore[call-arg]

    assert settings.nvdec_ffmpeg_path == "tools/ffmpeg/bin/ffmpeg.exe"
    assert settings.nvdec_ffprobe_path == "tools/ffmpeg/bin/ffprobe.exe"
    assert settings.nvdec_max_sessions == 3
    assert settings.nvdec_probe_timeout_s == 7
    assert settings.nvdec_restart_after_failures == 5


@pytest.mark.asyncio
async def test_worker_default_factory_is_the_fallback_ladder() -> None:
    cfg = CameraConfig(camera_id=11, rtsp_url="rtsp://x", worker_group=1, width=64, height=48)
    decoder = _FakeDecoder(frames=1, width=64, height=48)

    async def stop_stream_add(client, stream, fields, maxlen=None):  # type: ignore[no-untyped-def]
        worker._running = False
        return "1-0"

    worker = IngestionWorker(cfg, AsyncMock())  # no explicit factory

    with (
        patch("vms.ingestion.worker.create_decoder", return_value=decoder) as mock_factory,
        patch("vms.ingestion.worker.stream_add", side_effect=stop_stream_add),
        patch("vms.ingestion.worker.SHMSlot.create") as mock_create,
    ):
        mock_slot = MagicMock()
        mock_slot.name = "vms_cam_11"
        mock_slot.write.return_value = 1000
        mock_create.return_value = mock_slot
        await worker.start()

    mock_factory.assert_called_once_with("rtsp://x", camera_id=11, width=64, height=48)
    assert decoder.released is True


@pytest.mark.asyncio
async def test_worker_failure_threshold_semantics_unchanged_on_any_decoder() -> None:
    """A permanently failing decoder still walks backoff -> threshold -> inactive."""
    cfg = CameraConfig(camera_id=12, rtsp_url="rtsp://x", worker_group=1, width=64, height=48)

    class _DeadDecoder(_FakeDecoder):
        def read(self) -> tuple[bool, np.ndarray | None]:  # type: ignore[type-arg]
            return False, None

    dead = _DeadDecoder(frames=0)
    worker = IngestionWorker(cfg, AsyncMock(), decoder_factory=lambda _url: dead)
    worker._mark_camera_inactive = AsyncMock()  # type: ignore[method-assign]

    fake_settings = MagicMock()
    fake_settings.rtsp_failure_threshold = 2
    fake_settings.rtsp_backoff_delays_ms = [1]

    with (
        patch("vms.ingestion.worker.get_settings", return_value=fake_settings),
        patch("vms.ingestion.worker.asyncio.sleep", new=AsyncMock()),
        patch("vms.ingestion.worker.SHMSlot.create") as mock_create,
    ):
        mock_create.return_value = MagicMock()
        await worker.start()

    worker._mark_camera_inactive.assert_awaited_once()
    assert dead.released is True
