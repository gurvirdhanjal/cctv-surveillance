"""Thin gRPC wrapper around a single Triton-served ONNX model (Phase 6c).

Import of tritonclient is deferred via _import_grpc() so ORT-only deployments and
test suites that do not install tritonclient[grpc] still import this module without
error. The factory function is module-level so tests can patch it directly:
    patch("vms.inference.triton_client._import_grpc", return_value=grpc_mock)
"""

from __future__ import annotations

from typing import Any

import numpy as np


def _import_grpc() -> Any:  # Any: tritonclient.grpc has no stub; type is checked at call sites
    """Import tritonclient.grpc lazily; isolated here to allow test-time patching."""
    import tritonclient.grpc as _g

    return _g


class TritonModelClient:
    """Wraps one model hosted on a Triton Inference Server instance.

    Args:
        url: gRPC endpoint, e.g. ``"localhost:8001"``.
        model_name: Model name as registered in the Triton model repository.
        input_name: Name of the single input tensor (from the ONNX graph).
        output_names: Names of the output tensors to request, in the order the
            caller expects them in the returned list.
        input_dtype: Triton dtype string, e.g. ``"FP32"``, ``"FP16"``.
    """

    def __init__(
        self,
        url: str,
        model_name: str,
        input_name: str,
        output_names: list[str],
        input_dtype: str = "FP32",
    ) -> None:
        self._url = url
        self._model_name = model_name
        self._input_name = input_name
        self._output_names = output_names
        self._input_dtype = input_dtype

        _grpc = _import_grpc()
        self._grpc = _grpc
        self._client = _grpc.InferenceServerClient(url=url)

    def check_health(self) -> None:
        """Verify that the server is live and this model is ready.

        Raises:
            RuntimeError: If the server is unreachable or the model is not loaded.
                No silent fallback — a misconfigured endpoint is always an error.
        """
        if not self._client.is_server_live():
            raise RuntimeError(
                f"Triton server at {self._url!r} is not live — "
                "check that the server is running and the URL is correct."
            )
        if not self._client.is_model_ready(self._model_name):
            raise RuntimeError(
                f"Triton model {self._model_name!r} is not ready at {self._url!r} — "
                "check that the model repository is mounted and the model loaded."
            )

    def infer(self, tensor: np.ndarray) -> list[np.ndarray]:
        """Run inference on a single input tensor and return the requested outputs.

        Args:
            tensor: Input numpy array. Will be made C-contiguous if needed.

        Returns:
            List of numpy arrays in the same order as ``output_names``.
        """
        arr = np.ascontiguousarray(tensor)

        infer_input = self._grpc.InferInput(self._input_name, list(arr.shape), self._input_dtype)
        infer_input.set_data_from_numpy(arr)

        requested = [self._grpc.InferRequestedOutput(name) for name in self._output_names]

        result = self._client.infer(
            model_name=self._model_name,
            inputs=[infer_input],
            outputs=requested,
        )
        return [result.as_numpy(name) for name in self._output_names]
