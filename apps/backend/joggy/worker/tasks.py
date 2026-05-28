"""
RQ worker tasks — AI pipeline (Phase 3 implement จริง).
Claude (Tech Lead) — Phase 2 Day 4 skeleton; Phase 3 เพิ่ม ONNX pipeline
Phase 2 Day 5: process_erasure — Right to Erasure (D-014)

⚠️  Phase 3: import onnxruntime เท่านั้น — ห้าม import torch / paddle (D-021)
"""
from __future__ import annotations

import asyncio
import logging
import uuid as _uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select

from joggy.db.models import (
    ActorKind,
    AuditLog,
    ErasureRequest,
    ErasureStatus,
    FaceEmbedding,
    Photo,
)
from joggy.services import r2
from joggy.worker.db import worker_db_session

logger = logging.getLogger(__name__)


# ── Phase 3: Photo AI pipeline ────────────────────────────────────────────────

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


# ── Right to Erasure (D-014, SLA 24h) ────────────────────────────────────────

async def _process_erasure_async(erasure_id: str) -> dict:
    """Async implementation — called via asyncio.run() from process_erasure()."""
    async with worker_db_session() as db:
        # 1. Load ErasureRequest
        result = await db.execute(
            select(ErasureRequest).where(ErasureRequest.id == _uuid.UUID(erasure_id))
        )
        er = result.scalar_one_or_none()
        if not er:
            raise ValueError(f"ErasureRequest {erasure_id} not found")

        # 2. Mark as processing (so duplicate jobs skip it)
        er.status = ErasureStatus.processing
        db.add(er)
        await db.flush()

        # 3. Find all Photos for this event + bib
        photo_result = await db.execute(
            select(Photo).where(
                Photo.event_id == er.event_id,
                Photo.bib_number_nullable == er.bib_number,
            )
        )
        photos = list(photo_result.scalars().all())
        photo_ids = [p.id for p in photos]

        # 4. Delete FaceEmbeddings FIRST — biometric data must go before Photos (AGENTS.md)
        if photo_ids:
            await db.execute(
                delete(FaceEmbedding).where(FaceEmbedding.photo_id.in_(photo_ids))
            )

        # 5. Delete R2 objects — original + thumbnail (R2 delete_object is safe for missing keys)
        for photo in photos:
            try:
                r2.delete_object(photo.r2_key_original)
            except Exception as exc:
                logger.warning("R2 delete failed (original) photo=%s: %s", photo.id, exc)
            if photo.r2_key_thumbnail:
                try:
                    r2.delete_object(photo.r2_key_thumbnail)
                except Exception as exc:
                    logger.warning("R2 delete failed (thumbnail) photo=%s: %s", photo.id, exc)

        # 6. Delete Photo rows
        if photo_ids:
            await db.execute(
                delete(Photo).where(Photo.id.in_(photo_ids))
            )

        # 7. Mark ErasureRequest completed
        er.status = ErasureStatus.completed
        er.completed_at = datetime.now(timezone.utc)
        db.add(er)

        # 8. Audit log (actor = system — worker runs as system, not as partner)
        audit = AuditLog(
            actor_kind=ActorKind.system,
            action="erasure_completed",
            target_kind="erasure_request",
            target_id=er.id,
            context={
                "photos_deleted": len(photo_ids),
                "bib_number": er.bib_number,
                "event_id": str(er.event_id),
            },
        )
        db.add(audit)

        return {
            "erasure_id": erasure_id,
            "photos_deleted": len(photo_ids),
            "status": "completed",
        }


def process_erasure(erasure_id: str) -> dict:
    """
    RQ worker task: delete all photos + face embeddings for a runner bib.
    Implements Right to Erasure (D-014), SLA 24h from request.

    Deletion order (AGENTS.md security rule):
      1. FaceEmbeddings (biometric data — must go first)
      2. R2 objects (original + thumbnail)
      3. Photo DB rows

    On failure: sets ErasureRequest.status = failed and re-raises so RQ
    marks the job as failed (visible in RQ dashboard / retry logic).
    """
    try:
        return asyncio.run(_process_erasure_async(erasure_id))
    except Exception:
        logger.exception("process_erasure FAILED for erasure_id=%s", erasure_id)

        async def _mark_failed() -> None:
            async with worker_db_session() as db:
                result = await db.execute(
                    select(ErasureRequest).where(
                        ErasureRequest.id == _uuid.UUID(erasure_id)
                    )
                )
                er = result.scalar_one_or_none()
                if er and er.status != ErasureStatus.completed:
                    er.status = ErasureStatus.failed
                    db.add(er)

        asyncio.run(_mark_failed())
        raise
