"""
Public API — Partner-facing endpoints (D-018, Pull mode Phase 2).
Auth: X-API-Key: <partner_api_key>
ขอบเขต: photos:read + erasure:write เท่านั้น — ห้าม return face_embedding (AGENTS.md)
Claude (Tech Lead) — Phase 2 Day 3 skeleton
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from joggy.db.session import get_db
from joggy.middleware.partner_key import verify_partner_api_key, PartnerKeyClaims

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
    from fastapi import HTTPException
    import uuid
    from sqlalchemy import select
    from joggy.db.models import Photo, Checkpoint, AIReviewStatus
    from joggy.services.r2 import signed_url
    
    # ตรวจ scope
    if "public:photos:read" not in claims.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Missing required scope: public:photos:read"
        )
        
    try:
        event_uuid = uuid.UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid event_id")

    # SELECT photos WHERE event_id=? AND bib_number_nullable=? AND ai_review_status IN ('auto','manual_approved')
    stmt = (
        select(Photo, Checkpoint)
        .outerjoin(Checkpoint, Photo.checkpoint_id == Checkpoint.id)
        .where(
            Photo.event_id == event_uuid,
            Photo.bib_number_nullable == bib,
            Photo.ai_review_status.in_([AIReviewStatus.auto, AIReviewStatus.manual_approved])
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
            "checkpoint": (checkpoint.kind.value if hasattr(checkpoint.kind, "value") else str(checkpoint.kind)) if checkpoint else None
        })
        
    return {
        "event_id": event_id,
        "bib": bib,
        "photos": photos_data
    }


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
    Partner POST erasure request → สร้าง ErasureRequest row → enqueue RQ job.
    SLA: ลบภายใน 24h (sla_deadline = requested_at + 24h).
    Scope ที่ต้องมี: erasure:write

    Phase 2 Day 4+: implement จริง
    """
    from fastapi import HTTPException
    if "erasure:write" not in claims.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing required scope: erasure:write",
        )
    # TODO Phase 2 Day 4+: สร้าง ErasureRequest row + enqueue RQ job
    return {"status": "accepted", "sla_hours": 24}  # placeholder
