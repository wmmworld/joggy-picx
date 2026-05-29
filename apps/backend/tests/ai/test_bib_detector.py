import numpy as np
import pytest
from unittest.mock import MagicMock

from joggy.ai.bib_detector import BibBox, BibDetector

_INPUT_SIZE = 640


def _make_img(h: int = 480, w: int = 640) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _make_session(output: np.ndarray) -> MagicMock:
    sess = MagicMock()
    sess.run.return_value = [output]
    return sess


def test_detect_returns_bib_box_when_confident():
    # cx=320, cy=200, bw=100, bh=50 in 640-space; conf=0.9
    output = np.zeros((1, 5, 8400), dtype=np.float32)
    output[0, 0, 0] = 320.0   # cx
    output[0, 1, 0] = 200.0   # cy
    output[0, 2, 0] = 100.0   # bw
    output[0, 3, 0] = 50.0    # bh
    output[0, 4, 0] = 0.9     # conf
    result = BibDetector(_make_session(output)).detect(_make_img())
    assert isinstance(result, BibBox)
    assert result.confidence == pytest.approx(0.9)


def test_detect_returns_none_when_all_conf_zero():
    output = np.zeros((1, 5, 8400), dtype=np.float32)
    assert BibDetector(_make_session(output)).detect(_make_img()) is None


def test_detect_returns_none_below_threshold():
    output = np.zeros((1, 5, 8400), dtype=np.float32)
    output[0, 4, 0] = 0.3   # below _CONF_THRESHOLD (0.5)
    assert BibDetector(_make_session(output)).detect(_make_img()) is None


def test_detect_uses_images_input_key():
    output = np.zeros((1, 5, 8400), dtype=np.float32)
    sess = _make_session(output)
    BibDetector(sess).detect(_make_img())
    input_dict = sess.run.call_args[0][1]
    assert "images" in input_dict


def test_detect_bbox_coordinates_scale_to_original():
    # 640×640 model space → 640×480 original: sy = 640/480 ≈ 1.333, sx = 640/640 = 1.0
    # In impl: sx = INPUT_SIZE / w = 640/640 = 1.0; sy = INPUT_SIZE / h = 640/480 ≈ 1.333
    # cx=320, cy=200, bw=100, bh=50 → x1 = (320-50)/1.0 = 270, x2 = (320+50)/1.0 = 370
    output = np.zeros((1, 5, 8400), dtype=np.float32)
    output[0, 0, 0] = 320.0
    output[0, 1, 0] = 200.0
    output[0, 2, 0] = 100.0
    output[0, 3, 0] = 50.0
    output[0, 4, 0] = 0.9
    result = BibDetector(_make_session(output)).detect(_make_img(h=480, w=640))
    assert result is not None
    assert result.x1 == 270
    assert result.x2 == 370
    assert result.y1 == 131
    assert result.y2 == 168


def test_detect_clamps_bbox_to_image_bounds():
    # YOLO outputs bbox extending past 640×640 model space
    # Image is 320×320 so sx=sy=2.0; cx=635, bw=20 → x2 = (645)/2.0 = 322.5 → clamped to 320
    output = np.zeros((1, 5, 8400), dtype=np.float32)
    output[0, 0, 0] = 635.0   # cx near right edge
    output[0, 1, 0] = 635.0   # cy near bottom edge
    output[0, 2, 0] = 20.0    # bw — extends past edge
    output[0, 3, 0] = 20.0    # bh
    output[0, 4, 0] = 0.9
    result = BibDetector(_make_session(output)).detect(_make_img(h=320, w=320))
    assert result is not None
    assert result.x2 <= 320
    assert result.y2 <= 320
