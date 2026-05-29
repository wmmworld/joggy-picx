from unittest.mock import MagicMock, patch, call
import pytest

from joggy.ai.session import ModelSessions, load_sessions


def test_load_sessions_creates_five_sessions():
    with patch("joggy.ai.session.ort.InferenceSession") as mock_cls:
        mock_cls.return_value = MagicMock()
        sessions = load_sessions("fake_models")
    assert mock_cls.call_count == 5
    assert isinstance(sessions, ModelSessions)


def test_load_sessions_uses_correct_paths():
    with patch("joggy.ai.session.ort.InferenceSession") as mock_cls:
        mock_cls.return_value = MagicMock()
        load_sessions("/models")
    paths = [c.args[0].replace("\\", "/") for c in mock_cls.call_args_list]
    assert "/models/yolov8n_bib.onnx" in paths
    assert "/models/ocr_det.onnx" in paths
    assert "/models/ocr_rec.onnx" in paths
    assert "/models/buffalo_s/det_10g.onnx" in paths
    assert "/models/buffalo_s/w600k_r50.onnx" in paths


def test_load_sessions_uses_cpu_provider():
    with patch("joggy.ai.session.ort.InferenceSession") as mock_cls:
        mock_cls.return_value = MagicMock()
        load_sessions("/models")
    for c in mock_cls.call_args_list:
        assert c.kwargs.get("providers") == ["CPUExecutionProvider"]
