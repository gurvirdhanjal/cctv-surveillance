"""Tests for the MoViNet violence wrapper."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from vms.inference.violence import ViolenceModel


def test_missing_onnx_returns_none(tmp_path: Path) -> None:
    model = ViolenceModel(str(tmp_path / "nonexistent.onnx"))
    clip = np.zeros((16, 224, 224, 3), dtype=np.uint8)
    assert model.score(clip) is None


def test_score_returns_float_when_model_available(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeSession:
        def get_inputs(self):  # type: ignore[no-untyped-def]
            class _Input:
                name = "input"

            return [_Input()]

        def run(self, _outs, _inputs):  # type: ignore[no-untyped-def]
            return [np.array([[0.42]], dtype=np.float32)]

    class FakeOrt:
        @staticmethod
        def InferenceSession(path, providers):  # type: ignore[no-untyped-def]
            return FakeSession()

    import vms.inference.violence as mod

    monkeypatch.setattr(mod, "ort", FakeOrt(), raising=True)
    monkeypatch.setattr(mod.os.path, "exists", lambda p: True)
    model = ViolenceModel("/fake/path.onnx")
    clip = np.zeros((16, 224, 224, 3), dtype=np.uint8)
    score = model.score(clip)
    assert score == pytest.approx(0.42, abs=1e-3)
