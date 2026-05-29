import numpy as np
import pytest
from unittest.mock import MagicMock

from joggy.ai.face_embedder import FaceEmbedder, FaceResult


def _make_img(h: int = 480, w: int = 640) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _make_no_face_det_output():
    """9 output tensors all zeros — no face detected."""
    return [np.zeros((1, 1, 1), dtype=np.float32)] * 9


def _make_face_det_output():
    """
    Minimal det output: 1 face at stride 8 with conf=0.9.
    outputs[0]=scores_8, outputs[3]=bboxes_8, outputs[6]=landmarks_8
    """
    outputs = [np.zeros((1, 1, 1), dtype=np.float32)] * 9
    outputs[0] = np.array([[[0.9]]], dtype=np.float32)   # scores stride 8
    outputs[3] = np.array([[100.0, 100.0, 200.0, 200.0]], dtype=np.float32).reshape(1, 1, 4)
    lm = np.array([[[130, 140], [170, 140], [150, 160], [135, 180], [165, 180]]], dtype=np.float32)
    outputs[6] = lm
    return outputs


def test_embed_returns_none_when_no_face():
    det_sess = MagicMock()
    det_sess.run.return_value = _make_no_face_det_output()
    embed_sess = MagicMock()
    result = FaceEmbedder(det_sess, embed_sess).embed(_make_img())
    assert result is None
    embed_sess.run.assert_not_called()


def test_embed_returns_face_result_when_face_detected():
    det_sess = MagicMock()
    det_sess.run.return_value = _make_face_det_output()
    fake_vec = np.random.randn(1, 512).astype(np.float32)
    embed_sess = MagicMock()
    embed_sess.run.return_value = [fake_vec]
    result = FaceEmbedder(det_sess, embed_sess).embed(_make_img())
    assert isinstance(result, FaceResult)
    assert result.vector.shape == (512,)
    embed_sess.run.assert_called_once()


def test_embed_vector_is_l2_normalised():
    det_sess = MagicMock()
    det_sess.run.return_value = _make_face_det_output()
    raw_vec = np.ones((1, 512), dtype=np.float32) * 2.0
    embed_sess = MagicMock()
    embed_sess.run.return_value = [raw_vec]
    result = FaceEmbedder(det_sess, embed_sess).embed(_make_img())
    assert result is not None
    norm = float(np.linalg.norm(result.vector))
    assert norm == pytest.approx(1.0, abs=1e-5)


def test_embed_does_not_call_embed_when_no_face():
    det_sess = MagicMock()
    det_sess.run.return_value = _make_no_face_det_output()
    embed_sess = MagicMock()
    FaceEmbedder(det_sess, embed_sess).embed(_make_img())
    embed_sess.run.assert_not_called()


def test_embed_returns_none_when_embedding_is_zero():
    """Degenerate all-zero embedding output → None (would produce NaN in cosine sim)."""
    det_sess = MagicMock()
    det_sess.run.return_value = _make_face_det_output()
    embed_sess = MagicMock()
    embed_sess.run.return_value = [np.zeros((1, 512), dtype=np.float32)]
    result = FaceEmbedder(det_sess, embed_sess).embed(_make_img())
    assert result is None
