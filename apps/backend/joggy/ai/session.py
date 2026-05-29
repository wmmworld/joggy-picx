"""
ONNX session loader — preload all AI models at worker startup.
Claude (Tech Lead) — Phase 3

⚠️  D-021: onnxruntime ONLY — ห้าม import torch / paddle ในไฟล์นี้
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import onnxruntime as ort


@dataclass
class ModelSessions:
    """ONNX InferenceSession สำหรับ 5 model — ส่งผ่าน constructor ไม่ใช่ global."""
    yolo: ort.InferenceSession
    ocr_det: ort.InferenceSession
    ocr_rec: ort.InferenceSession
    face_det: ort.InferenceSession
    face_embed: ort.InferenceSession


def load_sessions(model_dir: str = "models") -> ModelSessions:
    """
    โหลด ONNX sessions ทั้งหมดตอน worker boot.
    เรียกครั้งเดียว — เก็บเป็น module-level singleton ใน tasks.py
    """
    def _load(*parts: str) -> ort.InferenceSession:
        full = os.path.join(model_dir, *parts)
        return ort.InferenceSession(full, providers=["CPUExecutionProvider"])

    return ModelSessions(
        yolo=_load("yolov8n_bib.onnx"),
        ocr_det=_load("ocr_det.onnx"),
        ocr_rec=_load("ocr_rec.onnx"),
        face_det=_load("buffalo_s", "det_10g.onnx"),
        face_embed=_load("buffalo_s", "w600k_r50.onnx"),
    )
