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
# 2026-06-05: 0.5 → 0.25 (YOLOv8 default). หลัง fine-tune mAP50=0.914 noise น้อย,
# ตัวกรอง 0.5 เคยตัดบิบที่ถูกแขน/มุมเอียงบังบางส่วน (CEO eyeball check บน F23_1516,
# JSP_0439). NMS @ 0.45 และ ai_review fallback ใน pipeline จับ false positive ที่เหลือ.
_CONF_THRESHOLD = 0.25
_IOU_THRESHOLD = 0.45   # NMS: drop boxes overlapping > 45% with a higher-conf box


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
        ตรวจหา bib เดียวที่ confidence สูงสุด (backward-compat helper).

        Pipeline เก่ายัง assume 1 bib/photo สำหรับ OCR — กดเก็บไว้เพื่อไม่ break.
        งานใหม่ที่ต้องการทุก bib ให้ใช้ `detect_all()`.
        """
        boxes = self.detect_all(img_bgr)
        return boxes[0] if boxes else None

    def detect_all(self, img_bgr: np.ndarray) -> list[BibBox]:
        """
        ตรวจหา bib ทั้งหมดในรูป BGR.
        Returns: list[BibBox] เรียงตาม confidence จากสูง→ต่ำ, ผ่าน NMS แล้ว.
        """
        h, w = img_bgr.shape[:2]
        tensor, sx, sy = self._preprocess(img_bgr)
        outputs = self._sess.run(None, {"images": tensor})
        return self._postprocess_all(outputs[0], sx, sy, w, h)

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

    def _postprocess_all(
        self, output: np.ndarray, sx: float, sy: float, w: int, h: int
    ) -> list[BibBox]:
        """
        Parse YOLOv8 output (1, 5, 8400) → list[BibBox] หลัง NMS.
        Each anchor: [cx, cy, w, h, conf] in model input coordinate space.
        """
        preds = output[0].T          # (8400, 5)
        confs = preds[:, 4]
        mask = confs > _CONF_THRESHOLD
        if not mask.any():
            return []
        kept = preds[mask]            # (N, 5) where N = #anchors above threshold

        # Convert all surviving anchors to original-image coordinates first,
        # then run NMS on those coordinates.
        boxes: list[BibBox] = []
        for row in kept:
            cx, cy, bw, bh = row[:4]
            conf = float(row[4])
            x1 = max(0, int((cx - bw / 2) / sx))
            y1 = max(0, int((cy - bh / 2) / sy))
            x2 = min(w, int((cx + bw / 2) / sx))
            y2 = min(h, int((cy + bh / 2) / sy))
            if x2 <= x1 or y2 <= y1:    # degenerate after clamp
                continue
            boxes.append(BibBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf))

        return _nms(boxes, _IOU_THRESHOLD)


def _iou(a: BibBox, b: BibBox) -> float:
    """Intersection-over-Union ระหว่างสองกล่อง."""
    ix1, iy1 = max(a.x1, b.x1), max(a.y1, b.y1)
    ix2, iy2 = min(a.x2, b.x2), min(a.y2, b.y2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    area_a = (a.x2 - a.x1) * (a.y2 - a.y1)
    area_b = (b.x2 - b.x1) * (b.y2 - b.y1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def _nms(boxes: list[BibBox], iou_threshold: float) -> list[BibBox]:
    """Greedy NMS: keep highest-conf first, drop anything overlapping > threshold."""
    ordered = sorted(boxes, key=lambda b: b.confidence, reverse=True)
    kept: list[BibBox] = []
    for box in ordered:
        if all(_iou(box, k) <= iou_threshold for k in kept):
            kept.append(box)
    return kept
