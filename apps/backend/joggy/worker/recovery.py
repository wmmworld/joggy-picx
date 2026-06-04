"""Self-healing watchdog for AI pipeline (DEV-3).

Closes the loop with DEV-1: when /ingest/photos accepts a photo but cannot
enqueue (Redis was down), we mark `context.enqueue_status="pending_enqueue"`
in the AuditLog instead of returning 500. This module re-enqueues those
photos once Redis recovers.

Trigger points:
- Backend startup (FastAPI lifespan hook) — covers "Redis was down at startup"
- Manual endpoint POST /internal/worker/reenqueue-pending — for ops debug

Idempotency:
- A second `enqueue_recovered` audit row is written per recovered photo,
  marking it as already handled. Subsequent runs skip photos that already
  have a recovered marker.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from joggy.db.models import ActorKind, AuditLog
from joggy.worker.queue import enqueue_process_photo

logger = logging.getLogger(__name__)


@dataclass
class RecoveryResult:
    """Summary of one recovery sweep."""
    pending_found: int = 0
    recovered: int = 0
    skipped_already_recovered: int = 0
    stopped_redis_still_down: bool = False


async def reenqueue_pending_photos(
    db: AsyncSession,
    *,
    max_age_hours: int = 24,
    limit: int = 100,
    enqueue_fn: Callable[[str], str] = enqueue_process_photo,
) -> RecoveryResult:
    """Re-enqueue photos whose initial enqueue failed (DEV-1 → DEV-3 self-heal).

    Args:
        db: Async DB session.
        max_age_hours: Don't try to recover photos older than this. Stale
            pending_enqueue records past this window are assumed unrecoverable
            (token may have rotated, event may have ended, etc.). Operators
            should investigate manually if recovery beyond 24h is needed.
        limit: Max audit rows to scan per sweep. Keeps each sweep bounded.
        enqueue_fn: Injectable for tests; default uses real RQ enqueue.

    Returns:
        RecoveryResult with counts.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    # AuditLog.created_at is TIMESTAMP WITHOUT TIME ZONE in DB → compare as naive
    cutoff_naive = cutoff.replace(tzinfo=None)

    # Find upload audit rows with pending_enqueue, newest-first within the window
    pending_stmt = (
        select(AuditLog)
        .where(
            AuditLog.action == "upload",
            AuditLog.created_at > cutoff_naive,
        )
        .order_by(AuditLog.created_at)
        .limit(limit)
    )
    result = await db.execute(pending_stmt)
    upload_rows = list(result.scalars().all())

    # Filter to ones flagged pending_enqueue (JSONB filter in SQL would be DB-specific;
    # post-filter in Python is fine at the scale of this watchdog — limit=100)
    pending = [
        row for row in upload_rows
        if row.context and row.context.get("enqueue_status") == "pending_enqueue"
    ]

    result = RecoveryResult(pending_found=len(pending))
    if not pending:
        return result

    # Look up which of these photos already have an enqueue_recovered audit row
    photo_ids = [row.target_id for row in pending if row.target_id is not None]
    if photo_ids:
        recovered_stmt = (
            select(AuditLog.target_id)
            .where(
                AuditLog.action == "enqueue_recovered",
                AuditLog.target_id.in_(photo_ids),
            )
        )
        recovered_result = await db.execute(recovered_stmt)
        already_recovered = {row for row in recovered_result.scalars().all()}
    else:
        already_recovered = set()

    for row in pending:
        if row.target_id in already_recovered:
            result.skipped_already_recovered += 1
            continue

        try:
            job_id = enqueue_fn(str(row.target_id))
        except Exception as exc:  # noqa: BLE001 — Redis still down, stop the sweep
            logger.warning(
                "Recovery sweep aborted: Redis still down (photo %s). %s",
                row.target_id, exc,
            )
            result.stopped_redis_still_down = True
            break

        recovery_audit = AuditLog(
            actor_kind=ActorKind.system,
            action="enqueue_recovered",
            target_kind="photo",
            target_id=row.target_id,
            context={
                "job_id": job_id,
                "original_audit_id": str(row.id),
                "original_uploaded_at": row.created_at.isoformat() if row.created_at else None,
            },
        )
        db.add(recovery_audit)
        result.recovered += 1
        logger.info("Re-enqueued photo %s as job %s", row.target_id, job_id)

    if result.recovered > 0:
        await db.commit()

    return result
