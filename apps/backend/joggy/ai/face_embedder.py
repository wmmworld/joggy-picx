"""
FaceEmbedder — InsightFace buffalo_s ONNX det + embed.
Claude (Tech Lead) — Phase 3

⚠️  D-021: onnxruntime ONLY
⚠️  SECURITY: face embedding = biometric data (D-014) — ห้าม return ผ่าน API

det_10g.onnx:   input "input.1" (1,3,640,640); outputs 9 tensors (stride 8/16/32)
w600k_r50.onnx: input "input.1" (1,3,112,112); output (1,512)
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort

_DET_SIZE = 640
_EMBED_SIZE = 112
_DET_CONF = 0.5

# ArcFace 5-point alignment template (from InsightFace repo)
_ARCFACE_DST = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)


@dataclass(frozen=True)
class FaceBox:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    landmarks: np.ndarray  # (5, 2)
    # NOTE: frozen=True still works with np.ndarray fields — it disables __setattr__
    # but does NOT make the instance hashable (numpy arrays are not hashable).
    # This is intentional: FaceBox is immutable by convention, not used as a dict key.


@dataclass(frozen=True)
class FaceResult:
    """512-dim L2-normalised face embedding — ⚠️ biometric data."""
    vector: np.ndarray   # shape (512,) float32 L2-normalised
    box: FaceBox


class FaceEmbedder:
    """InsightFace buffalo_s det + embed wrapper."""

    def __init__(
        self,
        det_sess: ort.InferenceSession,
        embed_sess: ort.InferenceSession,
    ) -> None:
        self._det = det_sess
        self._embed = embed_sess

    def embed(self, img_bgr: np.ndarray) -> FaceResult | None:
        """ตรวจหน้า → align → embed → return FaceResult | None."""
        tensor, scale = self._det_preprocess(img_bgr)
        det_outputs = self._det.run(None, {"input.1": tensor})
        face_box = self._parse_detections(det_outputs, scale)
        if face_box is None:
            return None
        aligned = self._align_face(img_bgr, face_box.landmarks)
        embed_tensor = self._embed_preprocess(aligned)
        raw = self._embed.run(None, {"input.1": embed_tensor})[0]
        vector = self._l2_normalize(raw[0])
        if vector is None:
            return None
        return FaceResult(vector=vector, box=face_box)

    # ── private ──────────────────────────────────────────────────────────────

    def _det_preprocess(self, img_bgr: np.ndarray) -> tuple[np.ndarray, float]:
        h, w = img_bgr.shape[:2]
        scale = _DET_SIZE / max(h, w)
        new_h, new_w = int(h * scale), int(w * scale)
        resized = cv2.cvtColor(
            cv2.resize(img_bgr, (new_w, new_h)), cv2.COLOR_BGR2RGB
        ).astype(np.float32)
        canvas = np.zeros((_DET_SIZE, _DET_SIZE, 3), dtype=np.float32)
        canvas[:new_h, :new_w] = resized
        return canvas.transpose(2, 0, 1)[np.newaxis], scale

    def _parse_detections(
        self, outputs: list[np.ndarray], scale: float
    ) -> FaceBox | None:
        """
        det_10g outputs[0..2] = scores per stride (8/16/32)
        outputs[3..5] = bboxes, outputs[6..8] = landmarks
        Pick highest-confidence face above _DET_CONF threshold.
        """
        all_scores, all_bboxes, all_lm = [], [], []
        for i in range(3):
            scores = outputs[i].reshape(-1)
            # Guard: skip stride if tensor is too small to hold any detection data.
            # In tests, mock tensors for empty strides may be (1,1,1) — size=1,
            # which cannot reshape to (-1, 4) or (-1, 5, 2).
            if outputs[3 + i].size % 4 != 0 or outputs[6 + i].size % 10 != 0:
                continue
            bboxes = outputs[3 + i].reshape(-1, 4)
            lmarks = outputs[6 + i].reshape(-1, 5, 2)
            # Align length: scores may differ from bbox count if tensor is padded
            n = min(len(scores), len(bboxes), len(lmarks))
            if n == 0:
                continue
            scores = scores[:n]
            bboxes = bboxes[:n]
            lmarks = lmarks[:n]
            mask = scores > _DET_CONF
            if mask.any():
                all_scores.append(scores[mask])
                all_bboxes.append(bboxes[mask] / scale)
                all_lm.append(lmarks[mask] / scale)
        if not all_scores:
            return None
        sc = np.concatenate(all_scores)
        bx = np.concatenate(all_bboxes)
        lm = np.concatenate(all_lm)
        best = int(sc.argmax())
        x1, y1, x2, y2 = bx[best]
        return FaceBox(
            x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2),
            confidence=float(sc[best]),
            landmarks=lm[best].astype(np.float32),
        )

    def _align_face(self, img_bgr: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
        """Affine-align face to 112×112 using 5-point landmarks."""
        M, _ = cv2.estimateAffinePartial2D(landmarks, _ARCFACE_DST, method=cv2.RANSAC)
        if M is None:
            h, w = img_bgr.shape[:2]
            s = min(h, w)
            crop = img_bgr[(h - s) // 2:(h + s) // 2, (w - s) // 2:(w + s) // 2]
            return cv2.resize(crop, (_EMBED_SIZE, _EMBED_SIZE))
        return cv2.warpAffine(img_bgr, M, (_EMBED_SIZE, _EMBED_SIZE))

    def _embed_preprocess(self, face_bgr: np.ndarray) -> np.ndarray:
        """BGR→RGB, normalize to [-1,1], NCHW float32 (InsightFace expects RGB)."""
        rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        arr = rgb.astype(np.float32)
        normalized = (arr / 127.5) - 1.0
        return normalized.transpose(2, 0, 1)[np.newaxis]

    @staticmethod
    def _l2_normalize(vec: np.ndarray) -> np.ndarray | None:
        norm = float(np.linalg.norm(vec))
        if norm < 1e-6:
            return None
        return (vec / norm).astype(np.float32)
