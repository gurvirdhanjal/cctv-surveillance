"""Unit tests for MinIOStorageBackend using moto S3 mock."""

from __future__ import annotations

import pytest
from moto import mock_aws


@pytest.fixture()
def minio_backend():  # type: ignore[no-untyped-def]
    """Provide a MinIOStorageBackend wired to a moto-mocked S3 endpoint."""
    with mock_aws():
        from vms.storage.backends import MinIOStorageBackend

        backend = MinIOStorageBackend(
            endpoint="",  # moto patches globally; endpoint is ignored
            access_key="test",
            secret_key="test",
            bucket="test-bucket",
        )
        yield backend


def test_minio_write_and_read(minio_backend) -> None:  # type: ignore[no-untyped-def]
    key = "thumbnails/2026/05/28/face.jpg"
    data = b"\xff\xd8\xff"
    minio_backend.write(key, data)
    assert minio_backend.read(key) == data


def test_minio_delete_removes_object(minio_backend) -> None:  # type: ignore[no-untyped-def]
    key = "thumbnails/2026/05/28/del.jpg"
    minio_backend.write(key, b"data")
    minio_backend.delete(key)
    assert not minio_backend.exists(key)


def test_minio_delete_missing_is_noop(minio_backend) -> None:  # type: ignore[no-untyped-def]
    minio_backend.delete("thumbnails/2026/05/28/nonexistent.jpg")


def test_minio_exists_false_for_missing(minio_backend) -> None:  # type: ignore[no-untyped-def]
    assert not minio_backend.exists("thumbnails/2026/05/28/missing.jpg")


def test_minio_url_is_presigned(minio_backend) -> None:  # type: ignore[no-untyped-def]
    key = "thumbnails/2026/05/28/presign.jpg"
    minio_backend.write(key, b"img")
    url = minio_backend.url(key)
    assert url
    assert key in url


def test_minio_bucket_auto_created() -> None:
    with mock_aws():
        import boto3

        from vms.storage.backends import MinIOStorageBackend

        MinIOStorageBackend(
            endpoint="",
            access_key="test",
            secret_key="test",
            bucket="auto-created-bucket",
        )
        s3 = boto3.client("s3", region_name="us-east-1")
        buckets = [b["Name"] for b in s3.list_buckets()["Buckets"]]
        assert "auto-created-bucket" in buckets
