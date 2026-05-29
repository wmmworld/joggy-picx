"""
BibDetector — YOLOv8-nano ONNX bib detection.
Claude (Tech Lead) — Phase 3

⚠️  D-021: onnxruntime ONLY
Model output format: (1, 5, 8400) — [cx, cy, w, h, conf] per anchor
Input tensor name: "images" (verify with session.get_inputs()[0].name)
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort

_INPUT_SIZE = 640
_CONF_THRESHOLD = 0.5


@dataclass(frozen=True)
class BibBox:
    """Bib bounding box ในพิกัดรูปต้นฉบับ."""
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


class BibDetector:
    """YOLOv8-nano wrapper สำหรับตรวจ bib number region."""

    def __init__(self, session: ort.InferenceSession) -> None:
        self._sess = session

    def detect(self, img_bgr: np.ndarray) -> BibBox | None:
        """
        ตรวจหา bib ในรูป BGR.
        Returns: BibBox ที่ confidence สูงสุด หรือ None ถ้าไม่เจอ.
        """
        h, w = img_bgr.shape[:2]
        tensor, sx, sy = self._preprocess(img_bgr)
        outputs = self._sess.run(None, {"images": tensor})
        return self._postprocess(outputs[0], sx, sy, w, h)

    # ── private ──────────────────────────────────────────────────────────────

    def _preprocess(self, img_bgr: np.ndarray) -> tuple[np.ndarray, float, float]:
        """Resize to 640×640, normalize [0,1], return NCHW float32 + scale factors."""
        h, w = img_bgr.shape[:2]
        sx = _INPUT_SIZE / w
        sy = _INPUT_SIZE / h
        resized = cv2.resize(img_bgr, (_INPUT_SIZE, _INPUT_SIZE))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = rgb.transpose(2, 0, 1)[np.newaxis].astype(np.float32) / 255.0
        return tensor, sx, sy

    def _postprocess(
        self, output: np.ndarray, sx: float, sy: float, w: int, h: int
    ) -> BibBox | None:
        """
        Parse YOLOv8 output (1, 5, 8400).
        Each anchor: [cx, cy, w, h, conf] in model input coordinate space.
        """
        preds = output[0].T          # (8400, 5)
        confs = preds[:, 4]
        mask = confs > _CONF_THRESHOLD
        if not mask.any():
            return None
        filtered_confs = confs[mask]
        best_idx = int(filtered_confs.argmax())
        best = preds[mask][best_idx]
        cx, cy, bw, bh = best[:4]
        conf = float(filtered_confs[best_idx])
        x1 = max(0, int((cx - bw / 2) / sx))
        y1 = max(0, int((cy - bh / 2) / sy))
        x2 = min(w, int((cx + bw / 2) / sx))
        y2 = min(h, int((cy + bh / 2) / sy))
        return BibBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf)
