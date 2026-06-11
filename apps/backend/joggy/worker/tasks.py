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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from joggy.ai.session import ModelSessions

from sqlalchemy import delete, select

from joggy.db.models import (
    ActorKind,
    AuditLog,
    ErasureRequest,
    ErasureStatus,
    FaceEmbedding,
    Photo,
    ReviewQueue,
)
from joggy.services import r2
from joggy.worker.db import worker_db_session

logger = logging.getLogger(__name__)


# ── Module-level ONNX session singleton ───────────────────────────────────────
# Loaded once when the RQ worker process starts.
# Lazy load on first call to avoid import-time side effects.
_sessions: "ModelSessions | None" = None  # type: ignore[assignment]


def _get_sessions() -> "ModelSessions":
    """
    Return preloaded ONNX sessions — load on first call (worker startup).

    Uses ``load_sessions_lenient()`` so missing ONNX files (OCR/face during
    Phase 6 incremental rollout) degrade gracefully instead of crashing the
    worker into an RQ retry loop. pipeline.py guards each session before use.
    """
    global _sessions
    if _sessions is None:
        import os
        from joggy.ai.session import load_sessions_lenient
        model_dir = os.environ.get("MODEL_DIR", "models")
        logger.info("Loading ONNX sessions from %s (lenient mode)...", model_dir)
        _sessions = load_sessions_lenient(model_dir)
    return _sessions


# ── Phase 3: Photo AI pipeline ────────────────────────────────────────────────

async def _process_photo_async(photo_id: str, sessions: "ModelSessions") -> dict:
    """Async wrapper — creates DB session and calls pipeline.run_pipeline()."""
    from joggy.worker.pipeline import run_pipeline
    async with worker_db_session() as db:
        return await run_pipeline(photo_id, db, sessions)


def process_photo(photo_id: str) -> dict:
    """
    RQ job entrypoint — AI pipeline for 1 photo.
    Preloads ONNX sessions on first call (worker startup).
    On failure: logs + re-raises (RQ will retry up to job_timeout).
    """
    sessions = _get_sessions()
    try:
        return asyncio.run(_process_photo_async(photo_id, sessions))
    except Exception:
        logger.exception("process_photo FAILED: photo_id=%s", photo_id)
        raise


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

        # Idempotency: if already completed, return early without re-processing
        if er.status == ErasureStatus.completed:
            return {"erasure_id": erasure_id, "photos_deleted": 0, "status": "completed"}

        # 2. Mark as processing (so duplicate jobs skip it)
        er.status = ErasureStatus.processing
        db.add(er)
        await db.flush()
        await db.commit()

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

        # 5a. Delete ReviewQueue rows (FK on photo_id → must go before Photo rows)
        if photo_ids:
            await db.execute(
                delete(ReviewQueue).where(ReviewQueue.photo_id.in_(photo_ids))
            )

        # 5b. Delete R2 objects — original + thumbnail (R2 delete_object is safe for missing keys)
        # Codex: ถ้า R2 delete fail ห้าม mark completed ไม่งั้นรูปอาจค้างใน storage โดยไม่มี DB row ให้ retry
        r2_failures: list[str] = []
        for photo in photos:
            try:
                r2.delete_object(photo.r2_key_original)
            except Exception as exc:
                logger.warning("R2 delete failed (original) photo=%s: %s", photo.id, exc)
                r2_failures.append(str(photo.id))
            if photo.r2_key_thumbnail:
                try:
                    r2.delete_object(photo.r2_key_thumbnail)
                except Exception as exc:
                    logger.warning("R2 delete failed (thumbnail) photo=%s: %s", photo.id, exc)
                    r2_failures.append(str(photo.id))

        if r2_failures:
            raise RuntimeError(f"R2 delete failed for {len(set(r2_failures))} photo(s)")

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
      2. ReviewQueue rows (FK constraint on photo_id)
      3. R2 objects (original + thumbnail)
      4. Photo DB rows

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

        try:
            asyncio.run(_mark_failed())
        except Exception:
            logger.exception("process_erasure: could not mark status=failed for %s", erasure_id)
        raise
