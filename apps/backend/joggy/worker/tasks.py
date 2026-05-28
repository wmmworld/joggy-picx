"""
RQ worker tasks — AI pipeline (Phase 3 implement จริง).
Claude (Tech Lead) — Phase 2 Day 4 skeleton; Phase 3 เพิ่ม ONNX pipeline

⚠️  Phase 3: import onnxruntime เท่านั้น — ห้าม import torch / paddle (D-021)
"""

import logging

logger = logging.getLogger(__name__)


def process_photo(photo_id: str) -> dict:
    """
    AI pipeline สำหรับ 1 รูป:
      1. โหลด JPEG จาก R2
      2. YOLOv8-nano ONNX → detect bib bounding box
      3. PaddleOCR ONNX → อ่านเลขบิบ (confidence score)
      4. InsightFace buffalo_s ONNX → extract face embedding (512-dim)
      5. UPDATE photos SET bib_number=?, bib_confidence=?, ai_review_status=?
      6. INSERT face_embeddings (ถ้ามีหน้า)
      7. ถ้า confidence ต่ำ → INSERT review_queue

    Phase 2: skeleton — log เท่านั้น
    Phase 3: implement จริง (Codex + Antigravity)
    """
    logger.info("process_photo called: photo_id=%s (Phase 3 pending)", photo_id)
    # TODO Phase 3:
    #   from joggy.worker.models import yolo_sess, ocr_sess, face_sess  # preloaded at boot
    #   ... ONNX inference pipeline ...
    return {"photo_id": photo_id, "status": "pending_phase3"}
