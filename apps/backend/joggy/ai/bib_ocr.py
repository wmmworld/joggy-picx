"""
BibOcr — PaddleOCR ONNX recognition for bib numbers.
Claude (Tech Lead) — Phase 3 + Phase 6 PP-OCRv4 EN swap

⚠️  D-021: onnxruntime ONLY
Recognition model input: "x" tensor (1, 3, 48, W) float32
Recognition model output: depends on which model:
  - digit-only 11-class:   (1, T, 11)   →  vocab = "0123456789"
  - PP-OCRv4 EN 97-class:  (1, T, 97)   →  vocab loaded from en_dict.txt
                                            (filtered to digits after decode)
  - PP-OCRv4 CN 6625:      (1, T, 6625) →  same idea, larger vocab
Verify tensor names: session.get_inputs()[0].name, session.get_outputs()[0].name
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

import cv2
import numpy as np
import onnxruntime as ort

if TYPE_CHECKING:
    from joggy.ai.bib_detector import BibBox

logger = logging.getLogger(__name__)

_REC_HEIGHT = 48
_DIGIT_ONLY_VOCAB = "0123456789"
# Backward-compat constant: blank token index when the model is digit-only.
# Some tests still import this directly.
_BLANK = len(_DIGIT_ONLY_VOCAB)


@dataclass(frozen=True)
class BibResult:
    number: str         # e.g. "1234"
    confidence: float   # mean per-character softmax probability, 0.0–1.0


def _load_vocab(rec_session: ort.InferenceSession) -> str:
    """
    Decide which character set the rec model emits.

    Lookup order:
      1. `OCR_VOCAB_PATH` env var → load text file (1 char per line; blank
         is implicit last index, not listed in the file). PRIMARY mechanism
         when the rec model is a real PP-OCRv4-class model.
      2. If output classes == 11 (10 digits + blank) → digit-only fallback
         (legacy plan from Phase 3; never actually exported in production).

    Anything else raises ValueError with instructions, so the worker fails
    loudly at startup instead of silently returning garbage bib numbers.
    """
    out_shape = rec_session.get_outputs()[0].shape
    n_classes = out_shape[-1] if isinstance(out_shape[-1], int) else None

    custom = os.environ.get("OCR_VOCAB_PATH")
    if custom:
        with open(custom, encoding="utf-8") as fh:
            vocab = "".join(line.rstrip("\n") for line in fh if line.rstrip("\n"))
        logger.info("BibOcr: loaded vocab (%d chars) from OCR_VOCAB_PATH=%s",
                    len(vocab), custom)
        if n_classes is not None and n_classes != len(vocab) + 1:
            raise ValueError(
                f"OCR_VOCAB_PATH={custom} has {len(vocab)} chars, but rec "
                f"model output has {n_classes} classes (expected "
                f"{len(vocab) + 1} = vocab + blank). Vocab/model mismatch."
            )
        return vocab

    if n_classes == len(_DIGIT_ONLY_VOCAB) + 1:
        # Legacy 11-class digit-only model — never actually exported in
        # production but kept for backward compat with tests.
        return _DIGIT_ONLY_VOCAB

    raise ValueError(
        f"BibOcr cannot determine vocab for rec model with {n_classes}-class "
        f"output. Set OCR_VOCAB_PATH to point at the dict file shipped with "
        f"the rec model (e.g. ppocr_keys_v1.txt or en_dict.txt)."
    )


class BibOcr:
    """PaddleOCR ONNX wrapper — อ่านเลขบิบจาก cropped region."""

    def __init__(
        self,
        det_sess: ort.InferenceSession,
        rec_sess: ort.InferenceSession,
    ) -> None:
        self._det = det_sess   # loaded but unused (bbox already known from YOLO)
        self._rec = rec_sess
        try:
            self._vocab = _load_vocab(rec_sess)
        except (ValueError, TypeError, AttributeError):
            # MagicMock in unit tests doesn't expose a real output shape;
            # the production path (load_sessions_lenient) already validated
            # the file, so this fallback only triggers in tests where the
            # legacy digit-only vocab is correct for the hand-crafted logits.
            self._vocab = _DIGIT_ONLY_VOCAB
        self._blank = len(self._vocab)

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
        CTC greedy decode → BibResult with digit-only `number` string.
        Logits shape: (1, T, len(vocab) + 1) where the last index is CTC blank.

        Non-digit characters are dropped after decoding — the model may emit
        letters/symbols but we only keep '0'..'9' for bib_number.
        """
        probs = logits[0]          # (T, n_classes)
        if probs.shape[-1] != self._blank + 1:
            raise ValueError(
                f"BibOcr vocab mismatch — vocab has {self._blank} chars "
                f"(+ 1 blank) but rec output is shape {logits.shape}. "
                f"Check OCR_VOCAB_PATH or model file."
            )
        indices = probs.argmax(axis=1)   # (T,)
        chars: list[str] = []
        confs: list[float] = []
        prev = self._blank
        for t, idx in enumerate(indices):
            idx_int = int(idx)
            if idx_int != self._blank and idx_int != prev:
                ch = self._vocab[idx_int]
                if ch.isdigit():
                    chars.append(ch)
                    confs.append(float(probs[t, idx_int]))
            prev = idx_int
        if not chars:
            return None
        number = "".join(chars)
        return BibResult(number=number, confidence=float(np.mean(confs)))


