"""Tests for TritonModelClient — gRPC wrapper with fail-fast health check (Phase 6c Task 1)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_grpc_module() -> MagicMock:
    """Return a mock that mimics the tritonclient.grpc namespace."""
    grpc = MagicMock()
    grpc.InferInput.return_value = MagicMock()
    grpc.InferRequestedOutput.return_value = MagicMock()
    mock_client_instance = MagicMock()
    mock_client_instance.is_server_live.return_value = True
    mock_client_instance.is_model_ready.return_value = True
    grpc.InferenceServerClient.return_value = mock_client_instance
    return grpc


def _make_client(
    grpc: MagicMock,
    *,
    url: str = "localhost:8001",
    model_name: str = "scrfd",
    input_name: str = "input",
    output_names: list[str] | None = None,
    input_dtype: str = "FP32",
) -> object:
    from vms.inference.triton_client import TritonModelClient

    with patch("vms.inference.triton_client._import_grpc", return_value=grpc):
        return TritonModelClient(
            url=url,
            model_name=model_name,
            input_name=input_name,
            output_names=output_names or ["output"],
            input_dtype=input_dtype,
        )


# ---------------------------------------------------------------------------
# infer()
# ---------------------------------------------------------------------------


def test_triton_client_infer_builds_input_and_returns_outputs() -> None:
    """infer() must build a correctly named/shaped InferInput and return outputs in order."""
    output_names = ["boxes", "scores"]
    arr = np.zeros((1, 3, 640, 640), dtype=np.float32)

    grpc = _mock_grpc_module()
    mock_infer_input = grpc.InferInput.return_value
    mock_server = grpc.InferenceServerClient.return_value

    sentinels = {name: np.ones((1,), dtype=np.float32) * i for i, name in enumerate(output_names)}
    mock_result = MagicMock()
    mock_result.as_numpy.side_effect = lambda name: sentinels[name]
    mock_server.infer.return_value = mock_result

    client = _make_client(grpc, model_name="scrfd", input_name="input", output_names=output_names)
    outputs = client.infer(arr)  # type: ignore[union-attr]

    # InferInput constructed with correct name, shape, dtype
    grpc.InferInput.assert_called_once_with("input", list(arr.shape), "FP32")
    mock_infer_input.set_data_from_numpy.assert_called_once()
    called_arr = mock_infer_input.set_data_from_numpy.call_args[0][0]
    assert called_arr.shape == arr.shape

    # InferRequestedOutput created for each output name
    assert grpc.InferRequestedOutput.call_count == len(output_names)
    requested = {call[0][0] for call in grpc.InferRequestedOutput.call_args_list}
    assert requested == set(output_names)

    # client.infer called with model name
    mock_server.infer.assert_called_once()
    call_kwargs = mock_server.infer.call_args[1]
    assert call_kwargs.get("model_name") == "scrfd"

    # Return value: list of numpy arrays in output_names order
    assert len(outputs) == len(output_names)
    for i, name in enumerate(output_names):
        np.testing.assert_array_equal(outputs[i], sentinels[name])


def test_triton_client_infer_passes_contiguous_array() -> None:
    """Non-contiguous arrays must be made contiguous before set_data_from_numpy."""
    # Transpose NHWC → NCHW produces a non-C-contiguous view.
    arr = np.zeros((1, 640, 640, 3), dtype=np.float32).transpose(0, 3, 1, 2)
    assert not arr.flags["C_CONTIGUOUS"]

    grpc = _mock_grpc_module()
    mock_infer_input = grpc.InferInput.return_value
    mock_server = grpc.InferenceServerClient.return_value
    mock_result = MagicMock()
    mock_result.as_numpy.return_value = np.zeros((1,))
    mock_server.infer.return_value = mock_result

    client = _make_client(grpc, output_names=["out"])
    client.infer(arr)  # type: ignore[union-attr]

    passed = mock_infer_input.set_data_from_numpy.call_args[0][0]
    assert passed.flags["C_CONTIGUOUS"]


# ---------------------------------------------------------------------------
# check_health()
# ---------------------------------------------------------------------------


def test_triton_client_check_health_passes_when_live_and_model_ready() -> None:
    """check_health() must not raise when server is live and model is ready."""
    grpc = _mock_grpc_module()
    client = _make_client(grpc, url="localhost:8001", model_name="scrfd")
    client.check_health()  # type: ignore[union-attr]  # must not raise


def test_triton_client_check_health_raises_when_server_not_live() -> None:
    """check_health() must raise RuntimeError (mentioning the URL) when server is not live."""
    grpc = _mock_grpc_module()
    grpc.InferenceServerClient.return_value.is_server_live.return_value = False

    client = _make_client(grpc, url="localhost:8001", model_name="scrfd")
    with pytest.raises(RuntimeError, match="localhost:8001"):
        client.check_health()  # type: ignore[union-attr]


def test_triton_client_check_health_raises_when_model_not_ready() -> None:
    """check_health() must raise RuntimeError (mentioning the model name) when model not ready."""
    grpc = _mock_grpc_module()
    grpc.InferenceServerClient.return_value.is_model_ready.return_value = False

    client = _make_client(grpc, url="localhost:8001", model_name="scrfd")
    with pytest.raises(RuntimeError, match="scrfd"):
        client.check_health()  # type: ignore[union-attr]


def test_triton_client_check_health_does_not_call_model_ready_when_server_dead() -> None:
    """If server is not live, model_ready must not be called (fail fast at first check)."""
    grpc = _mock_grpc_module()
    mock_server = grpc.InferenceServerClient.return_value
    mock_server.is_server_live.return_value = False

    client = _make_client(grpc)
    with pytest.raises(RuntimeError):
        client.check_health()  # type: ignore[union-attr]

    mock_server.is_model_ready.assert_not_called()
