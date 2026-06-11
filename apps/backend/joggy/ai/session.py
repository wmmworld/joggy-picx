"""
ONNX session loader — preload all AI models at worker startup.
Claude (Tech Lead) — Phase 3

⚠️  D-021: onnxruntime ONLY — ห้าม import torch / paddle ในไฟล์นี้

Two loaders:
  - load_sessions()         — STRICT. Raises FileNotFoundError if any model is
                              missing. Used by tests + manual sanity-check
                              scripts that want a hard fail.
  - load_sessions_lenient() — GRACEFUL. Returns a partial ModelSessions with
                              None for any missing file + a critical log line.
                              Used by the production RQ worker so a missing
                              OCR/face model doesn't crash the whole pipeline
                              and block photo ingest (Phase 6 — adding models
                              one at a time post-launch).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import onnxruntime as ort

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelSessions:
    """
    ONNX InferenceSession สำหรับ 5 model.
    Fields เป็น Optional หลัง 2026-06-11 (Phase 6 graceful skip) — pipeline.py
    ต้อง guard ทุก field ก่อนใช้.
    """
    yolo: Optional[ort.InferenceSession]
    ocr_det: Optional[ort.InferenceSession]
    ocr_rec: Optional[ort.InferenceSession]
    face_det: Optional[ort.InferenceSession]
    face_embed: Optional[ort.InferenceSession]


# Logical name -> path components under model_dir.
# Single source of truth for what the production worker expects.
_MODEL_PATHS: dict[str, tuple[str, ...]] = {
    "yolo": ("yolov8n_bib.onnx",),
    "ocr_det": ("ocr_det.onnx",),
    "ocr_rec": ("ocr_rec.onnx",),
    "face_det": ("buffalo_s", "det_10g.onnx"),
    "face_embed": ("buffalo_s", "w600k_r50.onnx"),
}


def _resolve_paths(model_dir: str) -> dict[str, str]:
    return {name: os.path.join(model_dir, *parts) for name, parts in _MODEL_PATHS.items()}


def load_sessions(model_dir: str = "models") -> ModelSessions:
    """
    STRICT loader — fail-fast ที่ startup ถ้าไฟล์ขาด.

    ใช้สำหรับ:
      - tests (assert error messages)
      - tools/train/test_holdout.py (dev sanity check)

    Production worker ใช้ ``load_sessions_lenient()`` แทน.
    """
    missing: list[str] = []
    resolved = _resolve_paths(model_dir)
    for path in resolved.values():
        if not os.path.isfile(path):
            missing.append(path)

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


def load_sessions_lenient(model_dir: str = "models") -> ModelSessions:
    """
    GRACEFUL loader — return ModelSessions with None for any missing file.
    Logs CRITICAL for every missing model so operators see it in journalctl.

    Pipeline guards each session before use; missing models translate to
    "skipped step" (no bib detection / no face embedding / etc.) rather
    than worker crash + RQ retry loop.

    This is the production default since 2026-06-11 — Joggy-PicX deploy
    started with only yolov8n_bib.onnx committed; OCR + face models are
    added incrementally without bringing the worker down.
    """
    resolved = _resolve_paths(model_dir)
    loaded: dict[str, Optional[ort.InferenceSession]] = {}
    missing: list[str] = []

    for name, path in resolved.items():
        if not os.path.isfile(path):
            missing.append(path)
            loaded[name] = None
            continue
        try:
            loaded[name] = ort.InferenceSession(path, providers=["CPUExecutionProvider"])
        except Exception as exc:  # noqa: BLE001 — onnxruntime raises broad
            logger.critical(
                "Failed to load ONNX session %s from %s — running pipeline "
                "without it: %s",
                name, path, exc,
            )
            loaded[name] = None

    if missing:
        bullet_list = "\n  - ".join(missing)
        logger.critical(
            "AI pipeline running in DEGRADED mode — %d ONNX model(s) missing "
            "under %r:\n  - %s\n\nAffected steps will be skipped. See "
            "apps/backend/models/README.md to populate.",
            len(missing), model_dir, bullet_list,
        )

    loaded_count = sum(1 for v in loaded.values() if v is not None)
    logger.info(
        "Loaded %d/%d ONNX sessions from %s (lenient mode)",
        loaded_count, len(resolved), model_dir,
    )
    return ModelSessions(**loaded)
