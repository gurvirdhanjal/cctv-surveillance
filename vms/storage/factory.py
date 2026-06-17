"""Factory for creating the process-wide StorageBackend singleton."""

from __future__ import annotations

from functools import lru_cache

from vms.config import get_settings
from vms.storage.backends import LocalStorageBackend, StorageBackend


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    """Return the process-wide StorageBackend instance (cached after first call)."""
    settings = get_settings()
    backend = settings.storage_backend
    if backend == "local":
        return LocalStorageBackend(settings.storage_local_dir)
    if backend == "minio":
        from vms.storage.backends import MinIOStorageBackend  # lazy: boto3 not always installed

        return MinIOStorageBackend(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
        )
    raise ValueError(f"Unknown storage_backend: {backend!r}. Expected 'local' or 'minio'.")


def clear_storage_cache() -> None:
    """Invalidate the get_storage() cache. Used in tests and on config reload."""
    get_storage.cache_clear()
