"""
Ingest API — รับรูปจาก Photographer (Pi / mobile) ผ่าน Per-Event Upload Token (D-017).
Auth: Authorization: Bearer <event_token>
Claude (Tech Lead) — Phase 2 Day 4
"""

import asyncio
import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from joggy.db.models import ActorKind, AuditLog, Photo
from joggy.db.session import get_db
from joggy.middleware.event_token import EventTokenClaims, verify_event_token
from joggy.services import r2
from joggy.worker.queue import enqueue_process_photo

router = APIRouter()

_security = HTTPBearer()

# ── Constants ─────────────────────────────────────────────────────────────────
_ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png"}
_MAX_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "/photos",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload photo — Photographer only (Event Token, D-017)",
    response_description="photo_id + RQ job_id",
)
async def upload_photo(
    file: UploadFile,
    device_id: str,
    captured_at: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(_security),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Flow:
      1. verify event_token (argon2 + expiry)
      2. validate file (MIME + size)
      3. compute sha256 → duplicate check (within event_id)
      4. upload original to R2
      5. INSERT photo row (ai_review_status=auto)
      6. enqueue RQ job
      7. INSERT audit_log
      8. return photo_id + job_id
    """

    # ── 1. Verify token ───────────────────────────────────────────────────────
    claims: EventTokenClaims = await verify_event_token(credentials=credentials, db=db)

    # ── 2. Validate file ──────────────────────────────────────────────────────
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {content_type}. ใช้ JPEG หรือ PNG เท่านั้น",
        )

    raw = await file.read()
    if len(raw) > _MAX_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"ไฟล์ใหญ่เกิน {_MAX_SIZE_BYTES // (1024*1024)} MB",
        )

    # ── 3. SHA-256 duplicate check ────────────────────────────────────────────
    sha256 = hashlib.sha256(raw).hexdigest()
    dup = await db.execute(
        select(Photo.id).where(
            Photo.event_id == claims.event_id,
            Photo.sha256 == sha256,
        )
    )
    if dup.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="รูปนี้อัปโหลดแล้ว (duplicate sha256 ใน event นี้)",
        )

    # ── 4. Upload to R2 ───────────────────────────────────────────────────────
    photo_id = uuid.uuid4()
    key_original = r2.r2_key_original(str(claims.event_id), str(photo_id))

    # run boto3 sync upload ใน thread pool (กัน block event loop)
    await asyncio.get_event_loop().run_in_executor(
        None, lambda: r2.upload_bytes(key_original, raw, content_type)
    )

    # ── 5. INSERT photo row ───────────────────────────────────────────────────
    captured_dt: datetime | None = None
    if captured_at:
        try:
            captured_dt = datetime.fromisoformat(captured_at)
            # DB column is TIMESTAMP WITHOUT TIME ZONE — strip tzinfo
            if captured_dt.tzinfo is not None:
                captured_dt = captured_dt.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            pass  # ignore malformed timestamp จากกล้อง

    photo = Photo(
        id=photo_id,
        event_id=claims.event_id,
        uploaded_by_event_token_id=claims.token_id,
        device_id=device_id,
        r2_key_original=key_original,
        sha256=sha256,
        mime_type=content_type,
        captured_at=captured_dt,
    )
    db.add(photo)
    await db.flush()  # ได้ photo.id ก่อน commit

    # ── 6. Enqueue RQ job ─────────────────────────────────────────────────────
    job_id = enqueue_process_photo(str(photo_id))

    # ── 7. Audit log ──────────────────────────────────────────────────────────
    audit = AuditLog(
        actor_event_token_id=claims.token_id,
        actor_kind=ActorKind.photographer,
        action="upload",
        target_kind="photo",
        target_id=photo_id,
        context={
            "device_id": device_id,
            "sha256": sha256,
            "size_bytes": len(raw),
            "job_id": job_id,
        },
    )
    db.add(audit)
    # session commit ผ่าน get_db() หลัง return

    return {
        "photo_id": str(photo_id),
        "job_id": job_id,
        "status": "queued",
    }
