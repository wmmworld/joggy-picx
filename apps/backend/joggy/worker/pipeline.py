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
from datetime import timedelta, timezone
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
    PhotoBib,
    ReviewQueue,
    ReviewQueueStatus,
)
from joggy.services import r2
from joggy.services.thumbnail import ThumbnailError, generate_thumbnail

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

    Graceful skip (2026-06-11): any ``sessions.*`` may be None when the
    corresponding ONNX file is missing. We instantiate AI services only when
    their sessions are present; downstream code guards each None case.
    """
    detector = BibDetector(sessions.yolo) if sessions.yolo is not None else None
    ocr = (
        BibOcr(sessions.ocr_det, sessions.ocr_rec)
        if sessions.ocr_det is not None and sessions.ocr_rec is not None
        else None
    )
    embedder = (
        FaceEmbedder(sessions.face_det, sessions.face_embed)
        if sessions.face_det is not None and sessions.face_embed is not None
        else None
    )

    photo_uuid = uuid.UUID(photo_id)

    # 1. Load Photo + Event
    photo: Photo | None = (await db.execute(
        select(Photo).where(Photo.id == photo_uuid)
    )).scalar_one_or_none()
    if photo is None:
        raise ValueError(f"Photo not found: {photo_id}")

    # Idempotency: if a human has already reviewed this photo, do not re-run AI
    if photo.ai_review_status in (
        AIReviewStatus.manual_approved,
        AIReviewStatus.manual_rejected,
    ):
        return {
            "photo_id": photo_id,
            "bib_number": photo.bib_number_nullable,
            "bib_confidence": photo.bib_confidence,
            "ai_review_status": photo.ai_review_status.value,
            "reid_match": None,
            "needs_review": False,
            "skipped_reason": "already_reviewed",
        }

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

    # 2.5 Thumbnail generation (best-effort — failures don't break AI pipeline)
    try:
        thumb_bytes = generate_thumbnail(img_bytes)
        thumb_key = r2.r2_key_thumbnail(str(photo.event_id), str(photo.id))
        r2.upload_bytes(thumb_key, thumb_bytes, content_type="image/jpeg")
        photo.r2_key_thumbnail = thumb_key
        logger.info(
            "Thumbnail generated for %s (%d bytes → %d bytes)",
            photo.id, len(img_bytes), len(thumb_bytes),
        )
    except ThumbnailError as e:
        logger.warning("Thumbnail generation failed for %s: %s", photo.id, e)

    # 3. Bib detection (all bibs) + OCR loop — ADR-0008 Phase A
    #    detect_all() returns every bib in frame (NMS filtered), sorted by conf desc.
    #    Each box is passed to OCR independently; only boxes with valid digit reads
    #    become PhotoBib rows.  The highest-confidence readable bib is also written
    #    to the deprecated Photo.bib_number_nullable field for backward-compat until
    #    the API layer migrates to joining photo_bibs (ADR-0008 Phase B).
    #
    #    Graceful skip: if YOLO is unavailable we cannot localize bibs at all;
    #    if YOLO works but OCR is unavailable we still record empty PhotoBib
    #    rows for review-queue triage but cannot read digits.
    all_boxes = detector.detect_all(img_bgr) if detector is not None else []
    bib_results = []
    if ocr is not None:
        h_img, w_img = img_bgr.shape[:2]
        for box in all_boxes:
            # YOLO bib_detector occasionally crops too tightly along the
            # number-strip edges (verified 2026-06-11: bib "4123" was
            # cropped down to only "30" → OCR happily reported "30" at
            # 1.00 confidence). Pad the bbox 20% in every direction
            # before passing to OCR so the full digit strip is included.
            # The PhotoBib row keeps the original (un-padded) bbox so the
            # frontend bounding-box overlay still highlights what YOLO
            # actually found.
            from joggy.ai.bib_detector import BibBox  # local to avoid import cycle
            pad_x = int((box.x2 - box.x1) * 0.20)
            pad_y = int((box.y2 - box.y1) * 0.20)
            padded = BibBox(
                x1=max(0, box.x1 - pad_x),
                y1=max(0, box.y1 - pad_y),
                x2=min(w_img, box.x2 + pad_x),
                y2=min(h_img, box.y2 + pad_y),
                confidence=box.confidence,
            )
            result = ocr.read(img_bgr, padded)
            if result is not None:
                bib_results.append((box, result))
                db.add(PhotoBib(
                    photo_id=photo_uuid,
                    bib_number=result.number,
                    confidence=result.confidence,
                    bbox_x1=box.x1,
                    bbox_y1=box.y1,
                    bbox_x2=box.x2,
                    bbox_y2=box.y2,
                ))

    # Best bib = first readable result (detect_all returns highest YOLO conf first)
    best_bib = bib_results[0][1] if bib_results else None

    # 4. Face embedding — skip if face models unavailable
    face_result = embedder.embed(img_bgr) if embedder is not None else None

    # 5. Determine status
    bib_ok = best_bib is not None and best_bib.confidence >= _BIB_CONF_THRESHOLD
    ai_status = AIReviewStatus.auto if bib_ok else AIReviewStatus.manual_pending

    # 5b. UPDATE Photo (deprecated fields — backward-compat until Phase B)
    photo.bib_number_nullable = best_bib.number if best_bib is not None else None
    photo.bib_confidence = best_bib.confidence if best_bib is not None else None
    photo.ai_review_status = ai_status
    db.add(photo)

    # 6. INSERT FaceEmbedding
    face_embedding_id: str | None = None
    if face_result is not None:
        # face_embeddings.retention_until column is TIMESTAMP WITHOUT TIME ZONE.
        # Cursor dashboard stores Event.end_at as tz-aware (ISO with `Z`), so
        # we strip tzinfo (convert to UTC first) before the arithmetic to
        # avoid asyncpg DataError. Mirrors the fix in api/ingest.py.
        # Found in production worker after face models were uploaded 2026-06-11.
        end_at = event.end_at
        if end_at.tzinfo is not None:
            end_at = end_at.astimezone(timezone.utc).replace(tzinfo=None)
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
        existing_rq = (await db.execute(
            select(ReviewQueue).where(ReviewQueue.photo_id == photo_uuid)
        )).scalar_one_or_none()
        if existing_rq is None:
            reason = "no_bib" if photo.bib_number_nullable is None else "low_ocr_conf"
            db.add(ReviewQueue(
                photo_id=photo_uuid,
                reason=reason,
                status=ReviewQueueStatus.pending,
            ))

    # 9. AuditLog — include which models were available so degraded runs are
    #    distinguishable from "real" no-bib results in post-hoc analysis.
    db.add(AuditLog(
        actor_kind=ActorKind.system,
        action="ai_pipeline_complete",
        target_kind="photo",
        target_id=photo_uuid,
        context={
            "bibs_detected": len(all_boxes),
            "bibs_readable": len(bib_results),
            "best_bib_number": photo.bib_number_nullable,
            "best_bib_confidence": photo.bib_confidence,
            "ai_status": photo.ai_review_status.value,
            "reid_match": reid_matched_bib,
            "face_embedding_id": face_embedding_id,
            "models_available": {
                "yolo": detector is not None,
                "ocr": ocr is not None,
                "face": embedder is not None,
            },
        },
    ))

    return {
        "photo_id": photo_id,
        "bibs_detected": len(all_boxes),
        "bibs_readable": len(bib_results),
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
        {"vec": vec_str, "event_id": event_id},
    )).fetchall()

    for bib_number, similarity in rows:
        if float(similarity) >= _REID_SIM_THRESHOLD:
            return str(bib_number)
    return None
