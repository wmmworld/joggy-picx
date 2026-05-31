"""
Internal API — Admin / Staff dashboard endpoints (D-019).
Auth: Supabase JWT (Authorization: Bearer <supabase_jwt>)
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from datetime import timedelta
from math import ceil

import argon2
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from joggy.api.schemas import (
    EventCreate,
    EventOut,
    EventStatusUpdate,
    PartnerKeyCreate,
    PartnerKeyOut,
    ReviewQueueItemOut,
    ReviewAction,
    PhotoItemOut,
    EventPhotosOut,
)
from joggy.db.models import (
    Checkpoint, Event, EventStatus, Organizer, PartnerApiKey,
    ReviewQueue, ReviewQueueStatus,
    Photo,
    AIReviewStatus,
    ActorKind, AuditLog,
)
from joggy.services import r2
from joggy.db.session import get_db
from joggy.middleware.internal_auth import InternalUserClaims, verify_internal_user

router = APIRouter()
_ph = argon2.PasswordHasher()


def _is_admin(claims: InternalUserClaims) -> bool:
    # Codex: normalize role เผื่อค่าใน DB เป็น enum/string
    return str(claims.role) in {"admin", "UserRole.admin"}


def _ensure_admin(claims: InternalUserClaims) -> None:
    # Codex: endpoint ที่มีสิทธิ์เฉพาะ admin ต้อง fail ด้วย 403
    if not _is_admin(claims):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


def _allowed_event_transition(current: str, new: str) -> bool:
    # Codex: enforce transition เฉพาะ planned -> active -> completed
    allowed = {
        "planned": {"active"},
        "active": {"completed"},
        "completed": set(),
    }
    return new in allowed.get(current, set())


async def _get_event_or_404(db: AsyncSession, event_id: uuid.UUID) -> Event:
    # Codex: helper โหลด event และโยน 404 เมื่อไม่พบ
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
    return event


def _ensure_staff_event_access(claims: InternalUserClaims, event: Event) -> None:
    # Codex: staff ต้องผ่านทั้ง organizer_scope + event_scope ตามข้อกำหนด
    if _is_admin(claims):
        return
    if event.organizer_id not in claims.organizer_scope or event.id not in claims.event_scope:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient scope")


def _ensure_staff_organizer_access(claims: InternalUserClaims, organizer_id: uuid.UUID) -> None:
    # Codex: key management เป็น organizer-level scope (D-018)
    if _is_admin(claims):
        return
    if organizer_id not in claims.organizer_scope:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient organizer scope")


@router.get("/events", response_model=list[EventOut], status_code=status.HTTP_200_OK)
async def list_events(
    db: AsyncSession = Depends(get_db),
    claims: InternalUserClaims = Depends(verify_internal_user),
) -> list[EventOut]:
    # Codex: admin เห็นทุก event; staff เห็นเฉพาะ organizer ใน scope
    stmt = select(Event).order_by(Event.start_at.desc())
    if not _is_admin(claims):
        if not claims.organizer_scope:
            return []
        stmt = stmt.where(Event.organizer_id.in_(claims.organizer_scope))
    result = await db.execute(stmt)
    events = list(result.scalars().all())

    return [
        EventOut(
            id=e.id,
            organizer_id=e.organizer_id,
            name=e.name,
            start_at=e.start_at,
            end_at=e.end_at,
            status=e.status.value if hasattr(e.status, "value") else str(e.status),
            allowed_origins=e.allowed_origins,
            retention_until=e.retention_until,
            created_at=e.created_at,
            checkpoints=[],
        )
        for e in events
    ]


@router.post("/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    payload: EventCreate,
    db: AsyncSession = Depends(get_db),
    claims: InternalUserClaims = Depends(verify_internal_user),
) -> EventOut:
    _ensure_admin(claims)
    if payload.end_at <= payload.start_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="end_at must be after start_at")

    organizer_result = await db.execute(select(Organizer).where(Organizer.id == payload.organizer_id))
    organizer = organizer_result.scalar_one_or_none()
    if not organizer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organizer not found")

    # Codex: retention default 30 วันหลังจบงานตาม schema docs
    retention_until = payload.end_at + timedelta(days=30)

    event = Event(
        organizer_id=payload.organizer_id,
        name=payload.name,
        start_at=payload.start_at,
        end_at=payload.end_at,
        status=EventStatus.planned,
        allowed_origins=payload.allowed_origins,
        retention_until=retention_until,
    )
    db.add(event)
    await db.flush()
    await db.refresh(event)

    return EventOut(
        id=event.id,
        organizer_id=event.organizer_id,
        name=event.name,
        start_at=event.start_at,
        end_at=event.end_at,
        status=event.status.value if hasattr(event.status, "value") else str(event.status),
        allowed_origins=event.allowed_origins,
        retention_until=event.retention_until,
        created_at=event.created_at,
        checkpoints=[],
    )


@router.get("/events/{event_id}", response_model=EventOut, status_code=status.HTTP_200_OK)
async def get_event_detail(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    claims: InternalUserClaims = Depends(verify_internal_user),
) -> EventOut:
    event = await _get_event_or_404(db, event_id)
    _ensure_staff_event_access(claims, event)

    checkpoint_result = await db.execute(
        select(Checkpoint).where(Checkpoint.event_id == event.id).order_by(Checkpoint.seq_order.asc())
    )
    checkpoints = list(checkpoint_result.scalars().all())

    return EventOut(
        id=event.id,
        organizer_id=event.organizer_id,
        name=event.name,
        start_at=event.start_at,
        end_at=event.end_at,
        status=event.status.value if hasattr(event.status, "value") else str(event.status),
        allowed_origins=event.allowed_origins,
        retention_until=event.retention_until,
        created_at=event.created_at,
        checkpoints=[
            {
                "id": cp.id,
                "event_id": cp.event_id,
                "name": cp.name,
                "kind": cp.kind.value if hasattr(cp.kind, "value") else str(cp.kind),
                "lat": cp.lat,
                "lng": cp.lng,
                "seq_order": cp.seq_order,
            }
            for cp in checkpoints
        ],
    )


@router.patch("/events/{event_id}", response_model=EventOut, status_code=status.HTTP_200_OK)
async def update_event_status(
    event_id: uuid.UUID,
    payload: EventStatusUpdate,
    db: AsyncSession = Depends(get_db),
    claims: InternalUserClaims = Depends(verify_internal_user),
) -> EventOut:
    event = await _get_event_or_404(db, event_id)
    _ensure_staff_event_access(claims, event)

    current = event.status.value if hasattr(event.status, "value") else str(event.status)
    next_status = payload.status
    if not _allowed_event_transition(current, next_status):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid event status transition")

    event.status = EventStatus(next_status)
    db.add(event)
    await db.flush()
    await db.refresh(event)

    checkpoint_result = await db.execute(
        select(Checkpoint).where(Checkpoint.event_id == event.id).order_by(Checkpoint.seq_order.asc())
    )
    checkpoints = list(checkpoint_result.scalars().all())

    return EventOut(
        id=event.id,
        organizer_id=event.organizer_id,
        name=event.name,
        start_at=event.start_at,
        end_at=event.end_at,
        status=event.status.value if hasattr(event.status, "value") else str(event.status),
        allowed_origins=event.allowed_origins,
        retention_until=event.retention_until,
        created_at=event.created_at,
        checkpoints=[
            {
                "id": cp.id,
                "event_id": cp.event_id,
                "name": cp.name,
                "kind": cp.kind.value if hasattr(cp.kind, "value") else str(cp.kind),
                "lat": cp.lat,
                "lng": cp.lng,
                "seq_order": cp.seq_order,
            }
            for cp in checkpoints
        ],
    )


@router.post(
    "/organizers/{organizer_id}/keys",
    response_model=PartnerKeyOut,
    status_code=status.HTTP_201_CREATED,
)
async def issue_partner_api_key(
    organizer_id: uuid.UUID,
    payload: PartnerKeyCreate,
    db: AsyncSession = Depends(get_db),
    claims: InternalUserClaims = Depends(verify_internal_user),
) -> PartnerKeyOut:
    _ensure_staff_organizer_access(claims, organizer_id)

    organizer_result = await db.execute(select(Organizer).where(Organizer.id == organizer_id))
    organizer = organizer_result.scalar_one_or_none()
    if not organizer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organizer not found")

    # Codex: 32 bytes random key แบบ hex, แสดง plaintext ครั้งเดียวแล้วเก็บเฉพาะ hash/prefix
    plaintext_key = secrets.token_hex(32)
    key_hash = _ph.hash(plaintext_key)
    key_prefix = plaintext_key[:8]

    partner_key = PartnerApiKey(
        organizer_id=organizer_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        scopes=payload.scopes,
        rate_limit_per_minute=payload.rate_limit_per_minute,
        issued_by_app_user_id=claims.user_id,
    )
    db.add(partner_key)
    await db.flush()
    await db.refresh(partner_key)

    return PartnerKeyOut(
        key_id=partner_key.id,
        key_prefix=partner_key.key_prefix,
        plaintext_key=plaintext_key,
        scopes=list(partner_key.scopes),
        rate_limit_per_minute=partner_key.rate_limit_per_minute,
        created_at=partner_key.created_at,
    )


@router.delete(
    "/organizers/{organizer_id}/keys/{key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_partner_api_key(
    organizer_id: uuid.UUID,
    key_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    claims: InternalUserClaims = Depends(verify_internal_user),
) -> None:
    _ensure_staff_organizer_access(claims, organizer_id)

    key_result = await db.execute(
        select(PartnerApiKey).where(
            PartnerApiKey.id == key_id,
            PartnerApiKey.organizer_id == organizer_id,
        )
    )
    partner_key = key_result.scalar_one_or_none()
    if not partner_key:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner API key not found")

    # Claude: func.now() เป็น SQL expression ใช้กับ ORM attribute ตรงๆ ไม่ได้ — ต้องใช้ Python datetime
    partner_key.revoked_at = datetime.now(timezone.utc)
    db.add(partner_key)


# ── Review Queue ─────────────────────────────────────────────────────────────

@router.get("/review-queue", response_model=list[ReviewQueueItemOut], status_code=status.HTTP_200_OK)
async def list_review_queue(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    claims: InternalUserClaims = Depends(verify_internal_user),
) -> list[ReviewQueueItemOut]:
    """List pending review-queue items for an event (max 200, sorted newest first)."""
    event = await _get_event_or_404(db, event_id)
    _ensure_staff_event_access(claims, event)

    stmt = (
        select(ReviewQueue, Photo, Checkpoint)
        .join(Photo, Photo.id == ReviewQueue.photo_id)
        .outerjoin(Checkpoint, Checkpoint.id == Photo.checkpoint_id)
        .where(
            and_(
                Photo.event_id == event_id,
                ReviewQueue.status.in_([ReviewQueueStatus.pending, ReviewQueueStatus.in_review]),
            )
        )
        .order_by(ReviewQueue.created_at.desc())
        .limit(200)
    )
    rows = (await db.execute(stmt)).all()

    result = []
    for rq, photo, checkpoint in rows:
        key = photo.r2_key_thumbnail or photo.r2_key_original
        url = r2.signed_url(key, expires_in=3600)
        result.append(
            ReviewQueueItemOut(
                queue_id=rq.id,
                photo_id=photo.id,
                reason=rq.reason,
                bib_number=photo.bib_number_nullable,
                bib_confidence=photo.bib_confidence,
                thumbnail_url=url,
                checkpoint_name=checkpoint.name if checkpoint else None,
                created_at=rq.created_at,
            )
        )
    return result


@router.patch("/review-queue/{queue_id}", status_code=status.HTTP_200_OK)
async def resolve_review_queue(
    queue_id: uuid.UUID,
    payload: ReviewAction,
    db: AsyncSession = Depends(get_db),
    claims: InternalUserClaims = Depends(verify_internal_user),
) -> dict:
    """Approve or reject a review queue item (with optional bib override)."""
    # 1. Load queue item
    rq_result = await db.execute(select(ReviewQueue).where(ReviewQueue.id == queue_id))
    rq = rq_result.scalar_one_or_none()
    if rq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review queue item not found")

    # 2. Idempotency guard
    if rq.status not in (ReviewQueueStatus.pending, ReviewQueueStatus.in_review):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Item already resolved")

    # 3. Load photo + event for scope check
    photo_result = await db.execute(select(Photo).where(Photo.id == rq.photo_id))
    photo = photo_result.scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    event = await _get_event_or_404(db, photo.event_id)
    _ensure_staff_event_access(claims, event)

    # 4. Resolve
    now = datetime.now(timezone.utc)
    if payload.action == "approve":
        rq.status = ReviewQueueStatus.approved
        photo.ai_review_status = AIReviewStatus.manual_approved
        if payload.decision_bib:
            rq.decision_bib = payload.decision_bib
            photo.bib_number_nullable = payload.decision_bib
    else:
        rq.status = ReviewQueueStatus.rejected
        photo.ai_review_status = AIReviewStatus.manual_rejected

    rq.resolved_at = now
    db.add(rq)
    db.add(photo)

    # 5. AuditLog
    db.add(AuditLog(
        actor_kind=ActorKind.internal_user,
        actor_app_user_id=claims.user_id,
        action="review_approved" if payload.action == "approve" else "review_rejected",
        target_kind="photo",
        target_id=photo.id,
        context={"queue_id": str(rq.id), "decision_bib": rq.decision_bib},
    ))

    await db.commit()
    return {"status": rq.status.value, "queue_id": str(rq.id)}


# ── Photo Gallery ─────────────────────────────────────────────────────────────

@router.get(
    "/events/{event_id}/photos",
    response_model=EventPhotosOut,
    status_code=status.HTTP_200_OK,
)
async def list_event_photos(
    event_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=24, ge=1, le=100),
    bib: str | None = Query(default=None),
    checkpoint_id: uuid.UUID | None = Query(default=None),
    ai_status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    claims: InternalUserClaims = Depends(verify_internal_user),
) -> EventPhotosOut:
    """Paginated photo gallery for an event — filter by bib/checkpoint/ai_status."""
    event = await _get_event_or_404(db, event_id)
    _ensure_staff_event_access(claims, event)

    # Validate ai_status query param
    ai_status_enum: AIReviewStatus | None = None
    if ai_status is not None:
        try:
            ai_status_enum = AIReviewStatus(ai_status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid ai_status '{ai_status}'. Valid: auto, manual_pending, manual_approved, manual_rejected",
            )

    # Build WHERE conditions
    conditions: list = [Photo.event_id == event_id]
    if bib:
        escaped_bib = bib.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        conditions.append(Photo.bib_number_nullable.ilike(f"%{escaped_bib}%", escape="\\"))
    if checkpoint_id:
        conditions.append(Photo.checkpoint_id == checkpoint_id)
    if ai_status_enum is not None:
        conditions.append(Photo.ai_review_status == ai_status_enum)

    # Count total matching records
    count_stmt = select(func.count(Photo.id)).where(and_(*conditions))
    total: int = (await db.execute(count_stmt)).scalar_one()

    # Fetch paginated results with checkpoint join
    stmt = (
        select(Photo, Checkpoint)
        .outerjoin(Checkpoint, Checkpoint.id == Photo.checkpoint_id)
        .where(and_(*conditions))
        .order_by(Photo.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(stmt)).all()

    # Build response items
    items = []
    for photo, checkpoint in rows:
        key = photo.r2_key_thumbnail or photo.r2_key_original
        url = r2.signed_url(key, expires_in=3600)
        items.append(
            PhotoItemOut(
                photo_id=photo.id,
                bib_number=photo.bib_number_nullable,
                bib_confidence=photo.bib_confidence,
                ai_review_status=(
                    photo.ai_review_status.value
                    if hasattr(photo.ai_review_status, "value")
                    else str(photo.ai_review_status)
                ),
                thumbnail_url=url,
                checkpoint_name=checkpoint.name if checkpoint else None,
                captured_at=photo.captured_at,
            )
        )

    pages = max(1, ceil(total / per_page))
    return EventPhotosOut(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )
