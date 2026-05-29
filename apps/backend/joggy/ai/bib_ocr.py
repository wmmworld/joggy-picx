"""
BibOcr — PaddleOCR ONNX recognition for bib numbers (digits only).
Claude (Tech Lead) — Phase 3

⚠️  D-021: onnxruntime ONLY
Recognition model input: "x" tensor (1, 3, 48, W) float32
Recognition model output: "softmax_0.tmp_0" (1, T, 11) — 10 digits + blank
Verify tensor names: session.get_inputs()[0].name, session.get_outputs()[0].name
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import numpy as np
import onnxruntime as ort

if TYPE_CHECKING:
    from joggy.ai.bib_detector import BibBox

_REC_HEIGHT = 48
_CHARS = "0123456789"
_BLANK = len(_CHARS)   # index 10 = CTC blank token


@dataclass(frozen=True)
class BibResult:
    number: str         # e.g. "1234"
    confidence: float   # mean per-character softmax probability, 0.0–1.0


class BibOcr:
    """PaddleOCR ONNX wrapper — อ่านเลขบิบจาก cropped region."""

    def __init__(
        self,
        det_sess: ort.InferenceSession,
        rec_sess: ort.InferenceSession,
    ) -> None:
        self._det = det_sess   # loaded but unused (bbox already known from YOLO)
        self._rec = rec_sess

    def read(self, img_bgr: np.ndarray, bbox: "BibBox | None") -> BibResult | None:
        """
        Crop bib region → อ่านเลข → BibResult | None.
        bbox=None → return None immediately.
        """
        if bbox is None:
            return None
        crop = img_bgr[bbox.y1:bbox.y2, bbox.x1:bbox.x2]
        if crop.size == 0:
            return None
        tensor = self._preprocess(crop)
        outputs = self._rec.run(None, {"x": tensor})
        return self._ctc_decode(outputs[0])

    # ── private ──────────────────────────────────────────────────────────────

    def _preprocess(self, crop_bgr: np.ndarray) -> np.ndarray:
        """Resize crop to height=48, normalize to [-1,1], NCHW float32."""
        h, w = crop_bgr.shape[:2]
        new_w = max(1, int(w * _REC_HEIGHT / h))
        resized = cv2.resize(crop_bgr, (new_w, _REC_HEIGHT))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
        normalized = (rgb / 127.5) - 1.0   # range [-1, 1]
        return normalized.transpose(2, 0, 1)[np.newaxis]  # (1, 3, 48, W)

    def _ctc_decode(self, logits: np.ndarray) -> BibResult | None:
        """
        CTC greedy decode — logits shape (1, T, 11).
        Remove blanks + consecutive duplicates, then assemble digit string.
        """
        probs = logits[0]          # (T, 11)
        if probs.shape[-1] != _BLANK + 1:
            raise ValueError(
                f"BibOcr expects {_BLANK + 1}-class output (10 digits + blank), "
                f"got shape {logits.shape}. Verify ocr_rec.onnx is a digit-only model."
            )
        indices = probs.argmax(axis=1)   # (T,)
        chars: list[str] = []
        confs: list[float] = []
        prev = _BLANK
        for t, idx in enumerate(indices):
            if idx != _BLANK and idx != prev:
                chars.append(_CHARS[idx])
                confs.append(float(probs[t, idx]))
            prev = int(idx)
        if not chars:
            return None
        number = "".join(chars)
        return BibResult(number=number, confidence=float(np.mean(confs)))
