"""
Public API — Partner-facing endpoints (D-018, Pull mode Phase 2).
Auth: X-API-Key: <partner_api_key>
ขอบเขต: photos:read + erasure:write เท่านั้น — ห้าม return face_embedding (AGENTS.md)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from joggy.db.models import (
    ActorKind,
    AIReviewStatus,
    AuditLog,
    Checkpoint,
    ErasureRequest,
    ErasureStatus,
    Event,
    Photo,
)
from joggy.db.session import get_db
from joggy.middleware.partner_key import PartnerKeyClaims, verify_partner_api_key
from joggy.services.r2 import signed_url
from joggy.worker.queue import enqueue_process_erasure

router = APIRouter()


# ── Photo Lookup ──────────────────────────────────────────────────────────────

@router.get(
    "/photos",
    status_code=status.HTTP_200_OK,
    summary="Get photos by bib number — Partner API (D-018)",
)
async def get_photos_by_bib(
    event_id: str,
    bib: str,
    db: AsyncSession = Depends(get_db),
    claims: PartnerKeyClaims = Depends(verify_partner_api_key),
) -> dict:
    """
    race-result.asia เรียก endpoint นี้ด้วย event_id + bib_number.
    คืน signed R2 URLs สำหรับรูปที่ match.

    ⚠️  ห้าม return face_embedding หรือ face_box coordinates ในทุกกรณี (AGENTS.md)
    """
    if "public:photos:read" not in claims.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required scope: public:photos:read",
        )

    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event_id")

    # Codex: public photo lookup must stay tenant-scoped to the partner's organizer.
    event_result = await db.execute(select(Event).where(Event.id == event_uuid))
    event = event_result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.organizer_id != claims.organizer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Event does not belong to your organization")

    stmt = (
        select(Photo, Checkpoint)
        .outerjoin(Checkpoint, Photo.checkpoint_id == Checkpoint.id)
        .where(
            Photo.event_id == event_uuid,
            Photo.bib_number_nullable == bib,
            Photo.ai_review_status.in_([AIReviewStatus.auto, AIReviewStatus.manual_approved]),
        )
    )

    result = await db.execute(stmt)
    rows = result.all()

    photos_data = []
    for photo, checkpoint in rows:
        photos_data.append({
            "photo_id": str(photo.id),
            "thumbnail_url": signed_url(photo.r2_key_thumbnail, expires_in=3600) if photo.r2_key_thumbnail else None,
            "original_url": signed_url(photo.r2_key_original, expires_in=3600),
            "captured_at": photo.captured_at.isoformat() if photo.captured_at else None,
            "checkpoint": (checkpoint.kind.value if hasattr(checkpoint.kind, "value") else str(checkpoint.kind)) if checkpoint else None,
        })

    return {"event_id": event_id, "bib": bib, "photos": photos_data}


# ── Erasure ───────────────────────────────────────────────────────────────────

@router.delete(
    "/erasure",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Right to Erasure — Partner requests photo deletion (D-014, SLA 24h)",
)
async def request_erasure(
    event_id: str,
    bib: str,
    reason: str | None = None,
    db: AsyncSession = Depends(get_db),
    claims: PartnerKeyClaims = Depends(verify_partner_api_key),
) -> dict:
    """
    Partner DELETE erasure request → สร้าง ErasureRequest row → enqueue RQ job.
    SLA: ลบภายใน 24h (sla_deadline = requested_at + 24h).
    Scope ที่ต้องมี: erasure:write
    """
    if "erasure:write" not in claims.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required scope: erasure:write",
        )

    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event_id")

    # Verify event exists and belongs to this partner's organizer
    event_result = await db.execute(select(Event).where(Event.id == event_uuid))
    event = event_result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    if event.organizer_id != claims.organizer_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Event does not belong to your organization")

    # Idempotency: prevent duplicate pending erasure for same event+bib
    existing_result = await db.execute(
        select(ErasureRequest).where(
            ErasureRequest.event_id == event_uuid,
            ErasureRequest.bib_number == bib,
            ErasureRequest.status == ErasureStatus.pending,
        )
    )
    if existing_result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Erasure request already pending for this bib",
        )

    now = datetime.now(timezone.utc)
    sla_deadline = now + timedelta(hours=24)

    er = ErasureRequest(
        event_id=event_uuid,
        bib_number=bib,
        requested_by_partner_api_key_id=claims.key_id,
        reason=reason,
        status=ErasureStatus.pending,
        sla_deadline=sla_deadline,
    )
    db.add(er)
    await db.flush()
    await db.refresh(er)

    try:
        job_id = enqueue_process_erasure(str(er.id))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to enqueue erasure job; please retry.",
        ) from exc

    # Audit log — actor = partner (the API key that requested erasure)
    audit = AuditLog(
        actor_partner_api_key_id=claims.key_id,
        actor_kind=ActorKind.partner,
        action="erasure_requested",
        target_kind="erasure_request",
        target_id=er.id,
        context={"bib": bib, "event_id": event_id, "job_id": job_id},
    )
    db.add(audit)

    return {
        "status": "accepted",
        "erasure_id": str(er.id),
        "sla_deadline": er.sla_deadline.isoformat(),
        "sla_hours": 24,
    }
