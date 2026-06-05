"""
ONNX session loader — preload all AI models at worker startup.
Claude (Tech Lead) — Phase 3

⚠️  D-021: onnxruntime ONLY — ห้าม import torch / paddle ในไฟล์นี้
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import onnxruntime as ort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelSessions:
    """ONNX InferenceSession สำหรับ 5 model — ส่งผ่าน constructor ไม่ใช่ global."""
    yolo: ort.InferenceSession
    ocr_det: ort.InferenceSession
    ocr_rec: ort.InferenceSession
    face_det: ort.InferenceSession
    face_embed: ort.InferenceSession


# Logical name -> path components under model_dir.
# Single source of truth for what the production worker expects.
_MODEL_PATHS: dict[str, tuple[str, ...]] = {
    "yolo": ("yolov8n_bib.onnx",),
    "ocr_det": ("ocr_det.onnx",),
    "ocr_rec": ("ocr_rec.onnx",),
    "face_det": ("buffalo_s", "det_10g.onnx"),
    "face_embed": ("buffalo_s", "w600k_r50.onnx"),
}


def load_sessions(model_dir: str = "models") -> ModelSessions:
    """
    โหลด ONNX sessions ทั้งหมดตอน worker boot.
    เรียกครั้งเดียว — เก็บเป็น module-level singleton ใน tasks.py.

    Pre-checks file existence first so the worker fails fast at startup
    with a clear, actionable error message instead of the cryptic
    ``[ONNXRuntimeError] : 3 : NO_SUCHFILE`` from onnxruntime.
    """
    missing: list[str] = []
    resolved: dict[str, str] = {}
    for name, parts in _MODEL_PATHS.items():
        full = os.path.join(model_dir, *parts)
        if not os.path.isfile(full):
            missing.append(full)
        resolved[name] = full

    if missing:
        bullet_list = "\n  - ".join(missing)
        raise FileNotFoundError(
            f"AI worker cannot start — {len(missing)} ONNX model file(s) "
            f"missing under {model_dir!r}:\n  - {bullet_list}\n\n"
            f"See apps/backend/models/README.md for how to populate this "
            f"directory (export scripts or InsightFace download).",
        )

    logger.info("Loading %d ONNX sessions from %s", len(resolved), model_dir)
    sessions = {
        name: ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        for name, path in resolved.items()
    }
    return ModelSessions(**sessions)
