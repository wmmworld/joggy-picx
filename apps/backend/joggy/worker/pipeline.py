"""
AI processing pipeline — orchestrates AI services + DB writes for 1 photo.
Claude (Tech Lead) — Phase 3

⚠️  D-021: onnxruntime ONLY — ห้าม import torch / paddle
⚠️  SECURITY: face embedding ห้าม return ผ่าน API (D-014, AGENTS.md)

Flow:
  1. Load Photo + Event from DB
  2. Download JPEG from R2
  3. BibDetector → BibOcr (bib_number, confidence)
  4. FaceEmbedder (512-dim vector)
  5. UPDATE photos
  6. INSERT face_embeddings (if face found)
  7. Cross-checkpoint Re-ID (if no bib + has face)
  8. INSERT review_queue if needed
  9. AuditLog
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import cv2
import numpy as np
from sqlalchemy import select, text

from joggy.ai.bib_detector import BibDetector
from joggy.ai.bib_ocr import BibOcr
from joggy.ai.face_embedder import FaceEmbedder
from joggy.db.models import (
    ActorKind,
    AIReviewStatus,
    AuditLog,
    Event,
    FaceEmbedding,
    Photo,
    ReviewQueue,
    ReviewQueueStatus,
)
from joggy.services import r2

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from joggy.ai.session import ModelSessions

logger = logging.getLogger(__name__)

_BIB_CONF_THRESHOLD = 0.70
_REID_SIM_THRESHOLD = 0.85


async def run_pipeline(
    photo_id: str,
    db: "AsyncSession",
    sessions: "ModelSessions",
) -> dict:
    """
    Main pipeline — called from tasks._process_photo_async().
    Returns summary dict. Raises on unrecoverable errors (triggers RQ retry).
    """
    detector = BibDetector(sessions.yolo)
    ocr = BibOcr(sessions.ocr_det, sessions.ocr_rec)
    embedder = FaceEmbedder(sessions.face_det, sessions.face_embed)

    photo_uuid = uuid.UUID(photo_id)

    # 1. Load Photo + Event
    photo: Photo | None = (await db.execute(
        select(Photo).where(Photo.id == photo_uuid)
    )).scalar_one_or_none()
    if photo is None:
        raise ValueError(f"Photo not found: {photo_id}")

    event: Event | None = (await db.execute(
        select(Event).where(Event.id == photo.event_id)
    )).scalar_one_or_none()
    if event is None:
        raise ValueError(f"Event not found: {photo.event_id}")

    # 2. Download + decode JPEG
    img_bytes = r2.download_bytes(photo.r2_key_original)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError(f"Cannot decode image for photo {photo_id}")

    # 3. Bib detection + OCR
    bbox = detector.detect(img_bgr)
    bib_result = ocr.read(img_bgr, bbox) if bbox is not None else None

    # 4. Face embedding
    face_result = embedder.embed(img_bgr)

    # 5. Determine status
    bib_ok = bib_result is not None and bib_result.confidence >= _BIB_CONF_THRESHOLD
    ai_status = AIReviewStatus.auto if bib_ok else AIReviewStatus.manual_pending

    # 5b. UPDATE Photo
    photo.bib_number_nullable = bib_result.number if bib_result is not None else None
    photo.bib_confidence = bib_result.confidence if bib_result is not None else 0.0
    photo.ai_review_status = ai_status
    db.add(photo)

    # 6. INSERT FaceEmbedding
    face_embedding_id: str | None = None
    if face_result is not None:
        end_at = event.end_at
        if end_at.tzinfo is None:
            end_at = end_at.replace(tzinfo=timezone.utc)
        retention_until = end_at + timedelta(days=7)
        fe = FaceEmbedding(
            photo_id=photo_uuid,
            embedding=face_result.vector.tolist(),
            face_box_x=face_result.box.x1,
            face_box_y=face_result.box.y1,
            face_box_w=face_result.box.x2 - face_result.box.x1,
            face_box_h=face_result.box.y2 - face_result.box.y1,
            detection_confidence=face_result.box.confidence,
            retention_until=retention_until,
        )
        db.add(fe)
        await db.flush()
        face_embedding_id = str(fe.id)

    # 7. Cross-checkpoint Re-ID (no bib + has face)
    reid_matched_bib: str | None = None
    if photo.bib_number_nullable is None and face_result is not None:
        reid_matched_bib = await _reid_query(db, photo.event_id, face_result.vector)
        if reid_matched_bib is not None:
            photo.bib_number_nullable = reid_matched_bib
            photo.ai_review_status = AIReviewStatus.auto
            db.add(photo)

    # 8. INSERT review_queue if still unresolved
    needs_review = (
        photo.bib_number_nullable is None
        or photo.ai_review_status == AIReviewStatus.manual_pending
    )
    if needs_review:
        reason = "no_bib" if photo.bib_number_nullable is None else "low_ocr_conf"
        db.add(ReviewQueue(
            photo_id=photo_uuid,
            reason=reason,
            status=ReviewQueueStatus.pending,
        ))

    # 9. AuditLog
    db.add(AuditLog(
        actor_kind=ActorKind.system,
        action="ai_pipeline_complete",
        target_kind="photo",
        target_id=photo_uuid,
        context={
            "bib_number": photo.bib_number_nullable,
            "bib_confidence": photo.bib_confidence,
            "ai_status": photo.ai_review_status.value,
            "reid_match": reid_matched_bib,
            "face_embedding_id": face_embedding_id,
        },
    ))

    await db.commit()
    return {
        "photo_id": photo_id,
        "bib_number": photo.bib_number_nullable,
        "bib_confidence": photo.bib_confidence,
        "ai_review_status": photo.ai_review_status.value,
        "reid_match": reid_matched_bib,
        "needs_review": needs_review,
    }


async def _reid_query(
    db: "AsyncSession",
    event_id: uuid.UUID,
    query_vector: np.ndarray,
) -> str | None:
    """
    pgvector cosine similarity search — same event only.
    Returns: bib_number หรือ None ถ้าไม่มี match เกิน threshold.
    """
    vec_str = "[" + ",".join(f"{v:.6f}" for v in query_vector.tolist()) + "]"
    rows = (await db.execute(
        text("""
            SELECT p.bib_number_nullable,
                   1 - (fe.embedding <=> CAST(:vec AS vector)) AS similarity
            FROM face_embeddings fe
            JOIN photos p ON p.id = fe.photo_id
            WHERE p.event_id = :event_id
              AND p.bib_number_nullable IS NOT NULL
            ORDER BY similarity DESC
            LIMIT 5
        """),
        {"vec": vec_str, "event_id": str(event_id)},
    )).fetchall()

    for bib_number, similarity in rows:
        if float(similarity) >= _REID_SIM_THRESHOLD:
            return str(bib_number)
    return None
