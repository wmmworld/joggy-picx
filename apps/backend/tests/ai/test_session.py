from unittest.mock import MagicMock, patch
import pytest

from joggy.ai.session import ModelSessions, load_sessions


def test_load_sessions_creates_five_sessions():
    with (
        patch("joggy.ai.session.os.path.isfile", return_value=True),
        patch("joggy.ai.session.ort.InferenceSession") as mock_cls,
    ):
        mock_cls.return_value = MagicMock()
        sessions = load_sessions("fake_models")
    assert mock_cls.call_count == 5
    assert isinstance(sessions, ModelSessions)


def test_load_sessions_uses_correct_paths():
    with (
        patch("joggy.ai.session.os.path.isfile", return_value=True),
        patch("joggy.ai.session.ort.InferenceSession") as mock_cls,
    ):
        mock_cls.return_value = MagicMock()
        load_sessions("/models")
    paths = [c.args[0].replace("\\", "/") for c in mock_cls.call_args_list]
    assert "/models/yolov8n_bib.onnx" in paths
    assert "/models/ocr_det.onnx" in paths
    assert "/models/ocr_rec.onnx" in paths
    assert "/models/buffalo_s/det_10g.onnx" in paths
    assert "/models/buffalo_s/w600k_r50.onnx" in paths


def test_load_sessions_uses_cpu_provider():
    with (
        patch("joggy.ai.session.os.path.isfile", return_value=True),
        patch("joggy.ai.session.ort.InferenceSession") as mock_cls,
    ):
        mock_cls.return_value = MagicMock()
        load_sessions("/models")
    for c in mock_cls.call_args_list:
        assert c.kwargs.get("providers") == ["CPUExecutionProvider"]


def test_load_sessions_raises_clear_error_when_files_missing():
    """Worker ต้อง fail-fast ด้วยข้อความที่บอกชัดว่าไฟล์ไหนหาย + ต้องทำอะไร."""
    # All files report missing
    with patch("joggy.ai.session.os.path.isfile", return_value=False):
        with pytest.raises(FileNotFoundError) as exc_info:
            load_sessions("/nonexistent")

    msg = str(exc_info.value)
    # Lists every expected file
    assert "yolov8n_bib.onnx" in msg
    assert "ocr_det.onnx" in msg
    assert "ocr_rec.onnx" in msg
    assert "det_10g.onnx" in msg
    assert "w600k_r50.onnx" in msg
    # Points to the README so the operator knows how to fix it
    assert "README.md" in msg
    # Reports a count so logs are scan-friendly
    assert "5" in msg


def test_load_sessions_reports_only_missing_files():
    """ถ้ามีไฟล์ครบ 4 หาย 1 → error mention เฉพาะที่หาย ไม่ noise."""
    def fake_isfile(path: str) -> bool:
        # All present except the YOLO model
        return "yolov8n_bib" not in path

    with patch("joggy.ai.session.os.path.isfile", side_effect=fake_isfile):
        with pytest.raises(FileNotFoundError) as exc_info:
            load_sessions("/models")

    msg = str(exc_info.value)
    assert "yolov8n_bib.onnx" in msg
    assert "ocr_det.onnx" not in msg
    assert "1" in msg   # missing count
