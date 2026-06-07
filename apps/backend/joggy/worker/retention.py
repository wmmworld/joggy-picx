"""
PDPA Auto-Delete Retention Worker — ADR-0004
=============================================

3 cron tasks ตาม ADR-0004:
  1. `delete_expired_photos`        — Photo.retention_until < now → R2 + DB cascade
  2. `delete_expired_face_embeddings` — FaceEmbedding.retention_until < now → DB
  3. `anonymize_expired_metadata`   — ConsentRecord ที่ photos หาย → NULL external_id

Trigger: systemd timer (24:00 ICT ทุกวัน) → `python -m joggy.worker.retention.run_all`
Audit:   per-photo / per-face / per-consent (granular per ADR-0004 rule #3)
Actor:   ActorKind.system (cron, ไม่ใช่ user action)

Failure semantics:
  - R2 delete fail → ห้ามลบ DB row (กัน orphan); audit log บันทึก failure;
    cron run ถัดมาจะ retry photo ตัวเดิม.
  - DB error → exception propagate → process exit code != 0 → systemd alerts.

Author: Claude (Tech Lead) — Phase 5 PDPA Cron, 2026-06-06
"""
from __future__ import annotations

import asyncio
import logging
import uuid as _uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select, update

from joggy.db.models import (
    ActorKind,
    AuditLog,
    ConsentRecord,
    FaceEmbedding,
    Photo,
    PhotoBib,
    ReviewQueue,
)
from joggy.services import r2
from joggy.worker.db import worker_db_session

logger = logging.getLogger(__name__)


# ── delete_expired_photos ─────────────────────────────────────────────────────


async def _delete_expired_photos_async() -> dict[str, int]:
    """
    Find photos where retention_until < now → R2 delete → DB cascade delete.
    Returns {deleted: N, failed: M}.
    """
    now = datetime.now(timezone.utc)
    deleted = 0
    failed = 0

    async with worker_db_session() as db:
        # 1. SELECT expired photos
        result = await db.execute(
            select(Photo).where(Photo.retention_until < now)
        )
        photos = list(result.scalars().all())

        if not photos:
            return {"deleted": 0, "failed": 0}

        # 2. R2 delete first (idempotent on missing keys) — collect successes
        ok_photo_ids: list[_uuid.UUID] = []
        for photo in photos:
            try:
                r2.delete_object(photo.r2_key_original)
                if photo.r2_key_thumbnail:
                    r2.delete_object(photo.r2_key_thumbnail)
                ok_photo_ids.append(photo.id)
            except Exception as exc:
                # Per ADR-0004 rule #6: hard delete only — ห้ามทิ้ง DB row
                # ค้างเพราะรูปยังอยู่ใน R2 → cron next run จะ retry
                logger.warning(
                    "retention: R2 delete failed photo=%s: %s", photo.id, exc
                )
                failed += 1
                db.add(
                    AuditLog(
                        actor_kind=ActorKind.system,
                        action="retention_delete_failed",
                        target_kind="photo",
                        target_id=photo.id,
                        context={
                            "error": str(exc),
                            "r2_key": photo.r2_key_original,
                        },
                    )
                )

        # 3. Cascade delete for photos where R2 succeeded
        #    Order: FaceEmbedding → ReviewQueue → PhotoBib → Photo
        #    (AGENTS.md: biometric data first; FK constraints next)
        if ok_photo_ids:
            await db.execute(
                delete(FaceEmbedding).where(FaceEmbedding.photo_id.in_(ok_photo_ids))
            )
            await db.execute(
                delete(ReviewQueue).where(ReviewQueue.photo_id.in_(ok_photo_ids))
            )
            await db.execute(
                delete(PhotoBib).where(PhotoBib.photo_id.in_(ok_photo_ids))
            )
            await db.execute(
                delete(Photo).where(Photo.id.in_(ok_photo_ids))
            )

            # 4. Audit log per-photo (granular per ADR-0004)
            for pid in ok_photo_ids:
                db.add(
                    AuditLog(
                        actor_kind=ActorKind.system,
                        action="retention_delete_photo",
                        target_kind="photo",
                        target_id=pid,
                        context={"reason": "retention_expired"},
                    )
                )
            deleted = len(ok_photo_ids)

    return {"deleted": deleted, "failed": failed}


# ── delete_expired_face_embeddings ───────────────────────────────────────────


async def _delete_expired_face_embeddings_async() -> dict[str, int]:
    """
    Find face embeddings where retention_until < now → DB delete.
    Biometric data — no R2 (face vectors only live in pgvector).
    """
    now = datetime.now(timezone.utc)
    async with worker_db_session() as db:
        result = await db.execute(
            select(FaceEmbedding).where(FaceEmbedding.retention_until < now)
        )
        faces = list(result.scalars().all())

        if not faces:
            return {"deleted": 0}

        face_ids = [f.id for f in faces]
        await db.execute(delete(FaceEmbedding).where(FaceEmbedding.id.in_(face_ids)))

        for fid in face_ids:
            db.add(
                AuditLog(
                    actor_kind=ActorKind.system,
                    action="retention_delete_face_embedding",
                    target_kind="face_embedding",
                    target_id=fid,
                    context={"reason": "retention_expired"},
                )
            )

        return {"deleted": len(face_ids)}


# ── anonymize_expired_metadata ───────────────────────────────────────────────


async def _anonymize_expired_metadata_async() -> dict[str, int]:
    """
    ConsentRecord ที่ผ่าน retention (photos already deleted) → NULL external_id.
    Keeps bib + event for analytics, drops link to runner identity.

    Selection criterion (ADR-0004): consent_at < now - 30d AND external_id IS NOT NULL.
    """
    now = datetime.now(timezone.utc)
    cutoff = now.replace(microsecond=0)
    async with worker_db_session() as db:
        # Find consent records older than 30 days that still have external_id
        result = await db.execute(
            select(ConsentRecord).where(
                ConsentRecord.partner_runner_external_id.isnot(None),
                ConsentRecord.consent_at < cutoff,
            )
        )
        records = list(result.scalars().all())

        if not records:
            return {"anonymized": 0}

        for rec in records:
            rec.partner_runner_external_id = None
            db.add(rec)
            db.add(
                AuditLog(
                    actor_kind=ActorKind.system,
                    action="retention_anonymize_metadata",
                    target_kind="consent_record",
                    target_id=rec.id,
                    context={
                        "reason": "retention_expired",
                        "bib_number": rec.bib_number,
                    },
                )
            )

        return {"anonymized": len(records)}


# ── Sync entrypoints (CLI / cron / RQ) ────────────────────────────────────────


def delete_expired_photos() -> dict[str, int]:
    """Sync wrapper for cron CLI."""
    try:
        return asyncio.run(_delete_expired_photos_async())
    except Exception:
        logger.exception("delete_expired_photos FAILED")
        raise


def delete_expired_face_embeddings() -> dict[str, int]:
    try:
        return asyncio.run(_delete_expired_face_embeddings_async())
    except Exception:
        logger.exception("delete_expired_face_embeddings FAILED")
        raise


def anonymize_expired_metadata() -> dict[str, int]:
    try:
        return asyncio.run(_anonymize_expired_metadata_async())
    except Exception:
        logger.exception("anonymize_expired_metadata FAILED")
        raise


def run_all_retention_jobs() -> dict[str, dict[str, int]]:
    """
    Run all 3 retention tasks sequentially.
    CLI entrypoint: `python -m joggy.worker.retention`
    Returns aggregated summary for systemd journal + monitoring.

    Each task isolated: failure in one doesn't stop the others.
    """
    summary: dict[str, dict[str, int]] = {}

    for name, fn in [
        ("photos", delete_expired_photos),
        ("face_embeddings", delete_expired_face_embeddings),
        ("metadata", anonymize_expired_metadata),
    ]:
        try:
            summary[name] = fn()
        except Exception as exc:
            logger.exception("retention task %s FAILED", name)
            summary[name] = {"error": 1, "message": str(exc)}  # type: ignore[dict-item]

    logger.info("retention.run_all_retention_jobs summary: %s", summary)
    return summary


# ── Module entrypoint for cron ───────────────────────────────────────────────

if __name__ == "__main__":  # pragma: no cover
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    result = run_all_retention_jobs()
    # Exit code 1 if any task errored — systemd uses this for alerting
    any_errored = any("error" in v for v in result.values())
    raise SystemExit(1 if any_errored else 0)
