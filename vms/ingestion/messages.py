"""Inter-process message types for the ingestion layer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FramePointer:
    """Lightweight Redis Stream payload pointing to a frame in shared memory."""

    cam_id: int
    shm_name: str
    seq_id: int
    timestamp_ms: int
    width: int
    height: int

    def to_redis_fields(self) -> dict[str, str]:
        return {
            "cam_id": str(self.cam_id),
            "shm_name": self.shm_name,
            "seq_id": str(self.seq_id),
            "timestamp_ms": str(self.timestamp_ms),
            "width": str(self.width),
            "height": str(self.height),
        }

    @classmethod
    def from_redis_fields(cls, fields: dict[str, str]) -> FramePointer:
        return cls(
            cam_id=int(fields["cam_id"]),
            shm_name=fields["shm_name"],
            seq_id=int(fields["seq_id"]),
            timestamp_ms=int(fields["timestamp_ms"]),
            width=int(fields["width"]),
            height=int(fields["height"]),
        )
