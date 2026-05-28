"""Helpers for writing face thumbnails and clip snapshots via a StorageBackend."""

from __future__ import annotations

from vms.storage.backends import StorageBackend, generate_key


def write_thumbnail(person_id: int, data: bytes, storage: StorageBackend) -> str:
    """Write *data* as a thumbnail for *person_id*. Returns the storage key."""
    key = generate_key("thumbnails")
    storage.write(key, data)
    return key


def write_snapshot(camera_id: int, data: bytes, storage: StorageBackend) -> str:
    """Write *data* as a clip snapshot from *camera_id*. Returns the storage key."""
    key = generate_key("snapshots")
    storage.write(key, data)
    return key
