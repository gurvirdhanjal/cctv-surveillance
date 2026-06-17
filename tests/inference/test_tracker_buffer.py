"""track_buffer is config-driven, not hard-coded (Phase 3 crosscam-accuracy, Task 8)."""

import yaml

from vms.config import get_settings
from vms.inference.tracker import resolve_tracker_config


def test_resolved_tracker_config_uses_settings_buffer(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("VMS_TRACKER_BUFFER_FRAMES", "150")
    get_settings.cache_clear()
    path = resolve_tracker_config()
    with open(path) as fh:
        data = yaml.safe_load(fh)
    assert data["track_buffer"] == 150
    get_settings.cache_clear()


def test_default_resolved_buffer_is_90() -> None:
    get_settings.cache_clear()
    path = resolve_tracker_config()
    with open(path) as fh:
        data = yaml.safe_load(fh)
    assert data["track_buffer"] == 90
    get_settings.cache_clear()
