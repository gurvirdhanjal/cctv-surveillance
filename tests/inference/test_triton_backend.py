"""Tests for TritonInferenceBackend — GPU kernel via gRPC (Phase 6c Task 4).

The identity guard test (test_triton_backend_embed_matches_ort_cosine) is the
most important: it verifies that the Triton backend's preprocessing+postprocessing
is identical to the ORT path when both receive the same raw kernel output.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np

from vms.inference.messages import FaceWithEmbedding

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_face(
    bbox: tuple[int, int, int, int] = (10, 10, 80, 80),
    *,
    add_keypoints: bool = False,
) -> FaceWithEmbedding:
    kps: tuple[tuple[float, float], ...] = (
        (20.0, 20.0),
        (60.0, 20.0),
        (40.0, 40.0),
        (25.0, 60.0),
        (55.0, 60.0),
    )
    return FaceWithEmbedding(
        bbox=bbox,
        confidence=0.95,
        embedding=(),
        keypoints=kps if add_keypoints else (),
    )


def _mock_clients() -> dict[str, MagicMock]:
    """Return 4 mock TritonModelClient instances (all health-checks pass by default)."""
    clients: dict[str, MagicMock] = {}
    for name in ("scrfd", "adaface", "transreid", "ppe"):
        m = MagicMock()
        m.check_health.return_value = None
        clients[name] = m
    return clients


def _make_triton_backend(clients: dict[str, MagicMock]) -> object:
    """Instantiate TritonInferenceBackend with pre-built mock clients injected via patch."""
    from vms.inference.backend import TritonInferenceBackend

    call_order = list(clients.values())
    call_iter = iter(call_order)

    def _factory(*args: object, **kwargs: object) -> MagicMock:
        return next(call_iter)

    with (
        patch("vms.inference.backend._discover_model_io", return_value=("input", ["output"])),
        patch("vms.inference.backend.TritonModelClient", side_effect=_factory),
    ):
        return TritonInferenceBackend(url="localhost:8001")


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


def test_triton_backend_init_health_checks_all_models() -> None:
    """__init__ must call check_health() on all four model clients."""
    clients = _mock_clients()
    _make_triton_backend(clients)

    for name, m in clients.items():
        m.check_health.assert_called_once(), f"check_health not called for {name}"


def test_triton_backend_init_raises_when_any_model_not_ready() -> None:
    """RuntimeError from any client's check_health() must propagate to the caller."""
    from vms.inference.backend import TritonInferenceBackend

    clients = _mock_clients()
    clients["adaface"].check_health.side_effect = RuntimeError("adaface not ready")

    call_iter = iter(clients.values())
    try:
        with (
            patch("vms.inference.backend._discover_model_io", return_value=("input", ["output"])),
            patch(
                "vms.inference.backend.TritonModelClient",
                side_effect=lambda *a, **k: next(call_iter),
            ),
        ):
            TritonInferenceBackend(url="localhost:8001")
        raise AssertionError("Expected RuntimeError not raised")
    except RuntimeError:
        pass  # expected


# ---------------------------------------------------------------------------
# detect() — letterbox preprocess + SCRFD decode
# ---------------------------------------------------------------------------


def test_triton_backend_detect_calls_scrfd_client_and_returns_tuple() -> None:
    """detect() must call scrfd_client.infer() and return a tuple (even when empty)."""
    clients = _mock_clients()
    # Return 9 empty outputs (SCRFD_10G_KPS format: 3 cls + 3 bbox + 3 kps outputs)
    clients["scrfd"].infer.return_value = [np.zeros((0, 1)) for _ in range(9)]

    backend = _make_triton_backend(clients)
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    result = backend.detect(frame)  # type: ignore[union-attr]

    clients["scrfd"].infer.assert_called_once()
    assert isinstance(result, tuple)


def test_triton_backend_detect_passes_blob_shape_to_client() -> None:
    """detect() must send a (1, 3, 640, 640) float32 blob to scrfd_client.infer()."""
    clients = _mock_clients()
    received: list[np.ndarray] = []

    def _capture(blob: np.ndarray) -> list[np.ndarray]:
        received.append(blob)
        return [np.zeros((0, 1)) for _ in range(9)]

    clients["scrfd"].infer.side_effect = _capture

    backend = _make_triton_backend(clients)
    backend.detect(np.zeros((480, 640, 3), dtype=np.uint8))  # type: ignore[union-attr]

    assert len(received) == 1
    assert received[0].shape == (1, 3, 640, 640)
    assert received[0].dtype == np.float32


# ---------------------------------------------------------------------------
# embed() — identity guard: Triton path == ORT path cosine ≥ 0.9999
# ---------------------------------------------------------------------------


def test_triton_backend_embed_matches_ort_cosine() -> None:
    """Triton and ORT paths must produce embeddings with cosine ≥ 0.9999 for the same raw tensor.

    Both paths apply identical preprocessing and L2-normalisation postprocessing.
    The mocked kernel returns the SAME raw tensor to both — this test verifies the
    shared pre/post code produces numerically equal results.
    """
    from vms.inference.embedder import AdaFaceEmbedder

    # A reproducible raw embedding (unnormalised, arbitrary values).
    rng = np.random.default_rng(seed=42)
    raw_embedding = rng.standard_normal(512).astype(np.float32)

    # --- ORT path -----------------------------------------------------------
    mock_sess = MagicMock()
    mock_sess.get_inputs.return_value = [MagicMock(name="input")]
    mock_sess.run.return_value = [raw_embedding[np.newaxis]]  # shape (1, 512)

    ort_embedder = AdaFaceEmbedder(session=mock_sess, min_face_px=1, min_blur=0.0)

    # Use random-noise frame so Laplacian variance is high (>> 25.0 default min_blur).
    frame_rng = np.random.default_rng(seed=7)
    frame = frame_rng.integers(50, 200, (200, 200, 3), dtype=np.uint8)
    face = _make_face(bbox=(10, 10, 100, 100))
    ort_result = ort_embedder.embed(face, frame)
    assert ort_result is not None, "ORT embedder returned None — check min_face_px / min_blur"

    # --- Triton path --------------------------------------------------------
    clients = _mock_clients()
    clients["adaface"].infer.return_value = [raw_embedding[np.newaxis]]  # same raw tensor

    backend = _make_triton_backend(clients)
    triton_result = backend.embed(face, frame)  # type: ignore[union-attr]
    assert triton_result is not None, "Triton backend embed() returned None unexpectedly"

    # --- Identity gate ------------------------------------------------------
    ort_emb = np.array(ort_result.embedding, dtype=np.float32)
    triton_emb = np.array(triton_result.embedding, dtype=np.float32)

    cosine = float(
        np.dot(ort_emb, triton_emb) / (np.linalg.norm(ort_emb) * np.linalg.norm(triton_emb))
    )
    assert cosine >= 0.9999, (
        f"ORT vs Triton embedding cosine={cosine:.6f} < 0.9999 — "
        "pre/post-processing divergence detected. STOP: mandatory /advisor before proceeding."
    )


def test_triton_backend_embed_returns_none_for_tiny_face() -> None:
    """embed() must return None when face bbox is smaller than min_face_px (quality gate)."""
    clients = _mock_clients()
    backend = _make_triton_backend(clients)

    tiny_face = _make_face(bbox=(10, 10, 14, 14))  # 4px — below any min_face_px
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    result = backend.embed(tiny_face, frame)  # type: ignore[union-attr]

    assert result is None
    clients["adaface"].infer.assert_not_called()


# ---------------------------------------------------------------------------
# score_ppe() — SH17 class indices
# ---------------------------------------------------------------------------


def test_triton_backend_score_ppe_uses_sh17_class_indices() -> None:
    """score_ppe() must map SH17 indices: helmet=10, vest=16, gloves=9, mask=5."""
    from vms.inference.ppe import _TARGET as SH17_TARGET

    # The Triton backend must use the same class-index mapping as PPEModel
    assert SH17_TARGET["helmet"] == 10
    assert SH17_TARGET["vest"] == 16
    assert SH17_TARGET["gloves"] == 9
    assert SH17_TARGET["mask"] == 5

    # Verify score_ppe() returns zero-scores (not None) for a valid crop with no detections
    clients = _mock_clients()
    # (1, 21, 8400) output — all zeros means no detections above threshold
    clients["ppe"].infer.return_value = [np.zeros((1, 21, 8400), dtype=np.float32)]

    backend = _make_triton_backend(clients)
    crop = np.full((100, 80, 3), 128, dtype=np.uint8)  # large enough to pass size gate
    result = backend.score_ppe(crop)  # type: ignore[union-attr]

    clients["ppe"].infer.assert_called_once()
    assert result is not None
    assert set(result.keys()) == {"helmet", "vest", "gloves", "mask"}


def test_triton_backend_score_ppe_returns_none_for_tiny_crop() -> None:
    """score_ppe() must return None when crop is smaller than the min-crop threshold."""
    clients = _mock_clients()
    backend = _make_triton_backend(clients)

    tiny_crop = np.zeros((10, 10, 3), dtype=np.uint8)
    result = backend.score_ppe(tiny_crop)  # type: ignore[union-attr]

    assert result is None
    clients["ppe"].infer.assert_not_called()
