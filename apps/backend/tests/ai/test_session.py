from unittest.mock import MagicMock, patch
import pytest

from joggy.ai.session import ModelSessions, load_sessions, load_sessions_lenient


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


# ── load_sessions_lenient (graceful skip mode) ───────────────────────────────


def test_lenient_loads_all_when_present():
    """Lenient mode with all files present = same as strict mode."""
    with (
        patch("joggy.ai.session.os.path.isfile", return_value=True),
        patch("joggy.ai.session.ort.InferenceSession") as mock_cls,
    ):
        mock_cls.return_value = MagicMock()
        sessions = load_sessions_lenient("/models")
    assert mock_cls.call_count == 5
    assert sessions.yolo is not None
    assert sessions.ocr_det is not None
    assert sessions.ocr_rec is not None
    assert sessions.face_det is not None
    assert sessions.face_embed is not None


def test_lenient_returns_none_for_missing_files():
    """OCR + face models missing → sessions have None there but yolo still loads."""
    def fake_isfile(path: str) -> bool:
        # Only yolo is present (matches Joggy-PicX production state 2026-06-11)
        return "yolov8n_bib" in path

    with (
        patch("joggy.ai.session.os.path.isfile", side_effect=fake_isfile),
        patch("joggy.ai.session.ort.InferenceSession") as mock_cls,
    ):
        mock_cls.return_value = MagicMock()
        sessions = load_sessions_lenient("/models")

    # Yolo loaded, the rest are None
    assert sessions.yolo is not None
    assert sessions.ocr_det is None
    assert sessions.ocr_rec is None
    assert sessions.face_det is None
    assert sessions.face_embed is None
    # InferenceSession was only called once (for yolo)
    assert mock_cls.call_count == 1


def test_lenient_does_not_raise_when_all_missing(caplog):
    """Even with no model files, lenient mode returns ModelSessions (all None)."""
    import logging

    with patch("joggy.ai.session.os.path.isfile", return_value=False):
        with caplog.at_level(logging.CRITICAL):
            sessions = load_sessions_lenient("/nonexistent")

    assert isinstance(sessions, ModelSessions)
    assert sessions.yolo is None
    assert sessions.ocr_det is None
    # CRITICAL log must be emitted so operators see the degraded state
    assert any(
        "DEGRADED mode" in rec.message and "5 ONNX model(s) missing" in rec.message
        for rec in caplog.records
    )
