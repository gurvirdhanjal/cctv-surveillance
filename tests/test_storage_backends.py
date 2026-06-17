"""Unit tests for vms.storage.backends — generate_key and StorageBackend Protocol."""

from __future__ import annotations

import pathlib
import re

from vms.storage.backends import StorageBackend, generate_key


def test_generate_key_matches_pattern() -> None:
    key = generate_key("thumbnails")
    assert re.fullmatch(r"thumbnails/\d{4}/\d{2}/\d{2}/[0-9a-f-]{36}\.jpg", key)


def test_generate_key_thumbnails_prefix() -> None:
    key = generate_key("thumbnails")
    assert key.startswith("thumbnails/")


def test_generate_key_snapshots_prefix() -> None:
    key = generate_key("snapshots")
    assert key.startswith("snapshots/")


def test_generate_key_custom_extension() -> None:
    key = generate_key("clips", ext="mp4")
    assert key.endswith(".mp4")
    assert re.fullmatch(r"clips/\d{4}/\d{2}/\d{2}/[0-9a-f-]{36}\.mp4", key)


def test_generate_key_default_extension_is_jpg() -> None:
    key = generate_key("thumbnails")
    assert key.endswith(".jpg")


def test_generate_key_successive_calls_differ() -> None:
    key1 = generate_key("thumbnails")
    key2 = generate_key("thumbnails")
    assert key1 != key2


def test_generate_key_uuid_segment_is_unique_across_many_calls() -> None:
    keys = {generate_key("thumbnails") for _ in range(50)}
    assert len(keys) == 50


def test_storage_backend_is_runtime_checkable_protocol() -> None:
    assert hasattr(StorageBackend, "__protocol_attrs__") or hasattr(StorageBackend, "_is_protocol")


def test_storage_backend_protocol_has_required_methods() -> None:
    required = {"write", "read", "delete", "exists", "url"}
    exposed = {name for name in dir(StorageBackend) if not name.startswith("_")}
    assert required.issubset(exposed)


def test_concrete_class_satisfying_protocol_passes_isinstance() -> None:
    class FakeBackend:
        def write(self, key: str, data: bytes) -> None:
            pass

        def read(self, key: str) -> bytes:
            return b""

        def delete(self, key: str) -> None:
            pass

        def exists(self, key: str) -> bool:
            return False

        def url(self, key: str) -> str:
            return f"file://{key}"

    assert isinstance(FakeBackend(), StorageBackend)


def test_class_missing_method_fails_isinstance() -> None:
    class IncompleteBackend:
        def write(self, key: str, data: bytes) -> None:
            pass

    assert not isinstance(IncompleteBackend(), StorageBackend)


# ---------------------------------------------------------------------------
# LocalStorageBackend
# ---------------------------------------------------------------------------


def test_local_write_creates_directories(tmp_path: pathlib.Path) -> None:
    from vms.storage.backends import LocalStorageBackend

    backend = LocalStorageBackend(str(tmp_path))
    key = "thumbnails/2026/05/28/abc.jpg"
    backend.write(key, b"hello")
    assert (tmp_path / key).read_bytes() == b"hello"


def test_local_read_returns_bytes(tmp_path: pathlib.Path) -> None:
    from vms.storage.backends import LocalStorageBackend

    backend = LocalStorageBackend(str(tmp_path))
    key = "snapshots/2026/05/28/test.jpg"
    backend.write(key, b"\x89PNG")
    assert backend.read(key) == b"\x89PNG"


def test_local_delete_removes_file(tmp_path: pathlib.Path) -> None:
    from vms.storage.backends import LocalStorageBackend

    backend = LocalStorageBackend(str(tmp_path))
    key = "thumbnails/2026/05/28/del.jpg"
    backend.write(key, b"data")
    backend.delete(key)
    assert not backend.exists(key)


def test_local_delete_missing_key_is_noop(tmp_path: pathlib.Path) -> None:
    from vms.storage.backends import LocalStorageBackend

    backend = LocalStorageBackend(str(tmp_path))
    backend.delete("thumbnails/2026/05/28/nonexistent.jpg")


def test_local_exists_returns_false_for_missing(tmp_path: pathlib.Path) -> None:
    from vms.storage.backends import LocalStorageBackend

    backend = LocalStorageBackend(str(tmp_path))
    assert not backend.exists("thumbnails/2026/05/28/missing.jpg")


def test_local_url_format(tmp_path: pathlib.Path) -> None:
    from vms.storage.backends import LocalStorageBackend

    backend = LocalStorageBackend(str(tmp_path))
    key = "thumbnails/2026/05/28/face.jpg"
    assert backend.url(key) == f"/media/{key}"


def test_local_backend_satisfies_protocol(tmp_path: pathlib.Path) -> None:
    from vms.storage.backends import LocalStorageBackend

    assert isinstance(LocalStorageBackend(str(tmp_path)), StorageBackend)
