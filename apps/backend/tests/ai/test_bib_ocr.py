import numpy as np
import pytest
from unittest.mock import MagicMock

from joggy.ai.bib_detector import BibBox
from joggy.ai.bib_ocr import BibOcr, BibResult, _BLANK


def _make_img(h: int = 100, w: int = 200) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _make_bbox(x1=0, y1=0, x2=100, y2=50) -> BibBox:
    return BibBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=0.9)


def _rec_session(logits: np.ndarray) -> MagicMock:
    sess = MagicMock()
    sess.run.return_value = [logits]
    return sess


def test_read_returns_none_when_bbox_none():
    ocr = BibOcr(MagicMock(), MagicMock())
    assert ocr.read(_make_img(), None) is None


def test_read_returns_bib_result_for_digit_sequence():
    # "1234" — T=4, C=11 (10 digits + blank=10)
    T, C = 4, 11
    logits = np.full((1, T, C), 0.01, dtype=np.float32)
    for t, idx in enumerate([1, 2, 3, 4]):
        logits[0, t, :] = 0.01
        logits[0, t, idx] = 0.95
    result = BibOcr(MagicMock(), _rec_session(logits)).read(_make_img(), _make_bbox())
    assert result is not None
    assert result.number == "1234"
    assert result.confidence > 0.9


def test_read_returns_none_when_all_blank():
    T, C = 5, 11
    logits = np.zeros((1, T, C), dtype=np.float32)
    logits[0, :, _BLANK] = 0.99   # all blanks
    assert BibOcr(MagicMock(), _rec_session(logits)).read(_make_img(), _make_bbox()) is None


def test_read_uses_x_input_key():
    T, C = 2, 11
    logits = np.zeros((1, T, C), dtype=np.float32)
    logits[0, 0, 1] = 0.95   # "1"
    rec_sess = _rec_session(logits)
    BibOcr(MagicMock(), rec_sess).read(_make_img(), _make_bbox())
    input_dict = rec_sess.run.call_args[0][1]
    assert "x" in input_dict


def test_read_confidence_is_mean_of_char_probs():
    T, C = 2, 11
    logits = np.zeros((1, T, C), dtype=np.float32)
    logits[0, 0, 1] = 0.8    # "1" at 0.8
    logits[0, 1, 2] = 0.6    # "2" at 0.6
    result = BibOcr(MagicMock(), _rec_session(logits)).read(_make_img(), _make_bbox())
    assert result is not None
    assert result.confidence == pytest.approx(0.7, abs=0.01)


def test_read_returns_none_when_empty_crop():
    """bbox with x1==x2 produces zero-size crop → None (no inference)."""
    rec_sess = MagicMock()
    ocr = BibOcr(MagicMock(), rec_sess)
    bbox = _make_bbox(x1=50, y1=50, x2=50, y2=80)  # zero width
    result = ocr.read(_make_img(), bbox)
    assert result is None
    rec_sess.run.assert_not_called()


def test_ctc_collapse_consecutive_duplicates():
    """Three consecutive frames predicting '1' → BibResult('1') per CTC rules."""
    T, C = 3, 11
    logits = np.zeros((1, T, C), dtype=np.float32)
    for t in range(T):
        logits[0, t, 1] = 0.9   # digit "1" repeated
    result = BibOcr(MagicMock(), _rec_session(logits)).read(_make_img(), _make_bbox())
    assert result is not None
    assert result.number == "1"


def test_ctc_decode_raises_on_wrong_shape():
    """Wrong vocab size should fail loudly, not silently corrupt."""
    # 1, T=2, C=20 — wrong! Should be 11 in the legacy digit-only fallback.
    logits = np.zeros((1, 2, 20), dtype=np.float32)
    logits[0, 0, 1] = 0.9
    with pytest.raises(ValueError, match="vocab mismatch"):
        BibOcr(MagicMock(), _rec_session(logits)).read(_make_img(), _make_bbox())
