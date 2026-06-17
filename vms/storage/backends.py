"""StorageBackend Protocol, generate_key helper, and concrete backend implementations."""

from __future__ import annotations

import contextlib
import pathlib
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StorageBackend(Protocol):
    """Duck-typing contract for all storage backends (local, MinIO, etc.)."""

    def write(self, key: str, data: bytes) -> None: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...
    def url(self, key: str) -> str: ...


def generate_key(prefix: str, ext: str = "jpg") -> str:
    """Return a content-addressed object key rooted at *prefix*.

    Format: ``{prefix}/{YYYY}/{MM}/{DD}/{uuid4}.{ext}``

    The date component uses UTC so keys are consistent across server timezones.
    """
    now = datetime.now(timezone.utc)
    return f"{prefix}/{now.year:04d}/{now.month:02d}/{now.day:02d}/{uuid.uuid4()}.{ext}"


class MinIOStorageBackend:
    """S3-compatible object storage backend (MinIO or AWS S3)."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
    ) -> None:
        import boto3  # type: ignore[import-untyped]  # lazy: not installed in all envs
        from botocore.config import Config  # type: ignore[import-untyped]

        self._bucket = bucket
        kwargs: dict[str, Any] = {
            "aws_access_key_id": access_key,
            "aws_secret_access_key": secret_key,
            "region_name": "us-east-1",
            "config": Config(signature_version="s3v4"),
        }
        if endpoint:
            kwargs["endpoint_url"] = endpoint
        self._client: Any = boto3.client("s3", **kwargs)
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        from botocore.exceptions import ClientError  # type: ignore[import-untyped]

        with contextlib.suppress(ClientError):
            self._client.head_bucket(Bucket=self._bucket)
            return
        self._client.create_bucket(Bucket=self._bucket)

    def write(self, key: str, data: bytes) -> None:
        import io

        self._client.put_object(Bucket=self._bucket, Key=key, Body=io.BytesIO(data))

    def read(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        result: bytes = response["Body"].read()
        return result

    def delete(self, key: str) -> None:
        from botocore.exceptions import ClientError

        with contextlib.suppress(ClientError):
            self._client.delete_object(Bucket=self._bucket, Key=key)

    def exists(self, key: str) -> bool:
        from botocore.exceptions import ClientError

        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError:
            return False

    def url(self, key: str) -> str:
        result: str = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=3600,
        )
        return result


class LocalStorageBackend:
    """Filesystem-backed storage. Stores objects under *base_dir* as relative keys."""

    def __init__(self, base_dir: str) -> None:
        self._base = pathlib.Path(base_dir)

    def write(self, key: str, data: bytes) -> None:
        dest = self._base / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)

    def read(self, key: str) -> bytes:
        return (self._base / key).read_bytes()

    def delete(self, key: str) -> None:
        (self._base / key).unlink(missing_ok=True)

    def exists(self, key: str) -> bool:
        return (self._base / key).exists()

    def url(self, key: str) -> str:
        return f"/media/{key}"
