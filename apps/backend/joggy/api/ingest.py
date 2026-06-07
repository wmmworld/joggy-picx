"""
Ingest API — รับรูปจาก Photographer (Pi / mobile) ผ่าน Per-Event Upload Token (D-017).
Auth: Authorization: Bearer <event_token>
Claude (Tech Lead) — Phase 2 Day 4
"""

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from joggy.db.models import ActorKind, AuditLog, Event, Photo
from joggy.db.session import get_db
from joggy.middleware.event_token import EventTokenClaims, verify_event_token
from joggy.middleware.rate_limit import check_rate_limit
from joggy.services import r2
from joggy.worker.queue import enqueue_process_photo

logger = logging.getLogger(__name__)

router = APIRouter()

_security = HTTPBearer()

# ── Constants ─────────────────────────────────────────────────────────────────
_ALLOWED_MIME = {"image/jpeg", "image/jpg", "image/png"}
_MAX_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB
_READ_CHUNK_BYTES = 1024 * 1024
_INGEST_RATE_LIMIT_PER_MINUTE = 120


async def _read_upload_limited(file: UploadFile) -> bytes:
    # Codex: อ่านเป็น chunk เพื่อ reject ไฟล์ใหญ่ทันทีที่เกิน limit แทนการดึงทั้ง body เข้าหน่วยความจำก่อน
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"ไฟล์ใหญ่เกิน {_MAX_SIZE_BYTES // (1024*1024)} MB",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _detect_image_mime(raw: bytes) -> str | None:
    # Codex: magic-byte check ป้องกัน client spoof Content-Type เป็น image/jpeg ทั้งที่ payload ไม่ใช่รูป
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "/photos",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload photo — Photographer only (Event Token, D-017)",
    response_description="photo_id + RQ job_id",
)
async def upload_photo(
    file: UploadFile,
    response: Response,
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
    await check_rate_limit(
        key_id=f"event-token:{claims.token_id}",
        limit_per_minute=_INGEST_RATE_LIMIT_PER_MINUTE,
        response=response,
    )

    # ── 2. Validate file ──────────────────────────────────────────────────────
    content_type = (file.content_type or "").lower()
    if content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {content_type}. ใช้ JPEG หรือ PNG เท่านั้น",
        )

    raw = await _read_upload_limited(file)
    detected_mime = _detect_image_mime(raw)
    if detected_mime is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="ไฟล์ต้องเป็น JPEG หรือ PNG ที่ตรวจสอบ magic bytes ได้",
        )
    content_type = detected_mime

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

    # PDPA ADR-0004: Photo.retention_until = event.end_at + 30d.
    # ต้อง set ตอน insert ไม่งั้น cron retention.delete_expired_photos จะหารูปไม่เจอ
    # (`retention_until < now()` ไม่ match NULL → รูปค้างถาวร, PDPA fail)
    event_row = await db.execute(
        select(Event.end_at).where(Event.id == claims.event_id)
    )
    end_at = event_row.scalar_one()
    photo_retention_until = end_at + timedelta(days=30)

    photo = Photo(
        id=photo_id,
        event_id=claims.event_id,
        uploaded_by_event_token_id=claims.token_id,
        device_id=device_id,
        r2_key_original=key_original,
        sha256=sha256,
        mime_type=content_type,
        captured_at=captured_dt,
        retention_until=photo_retention_until,
    )
    db.add(photo)
    await db.flush()  # ได้ photo.id ก่อน commit

    # ── 6. Enqueue RQ job (DEV-1: graceful if Redis is down) ──────────────────
    # If Redis is unreachable, do NOT roll back the photo. The row + R2 object
    # are durable, and a watchdog (DEV-3) can re-enqueue once Redis recovers.
    # Returning 500 here caused infinite Pi retry + R2 duplicates on 2026-06-04.
    job_id: str | None
    enqueue_status = "queued"
    try:
        job_id = enqueue_process_photo(str(photo_id))
    except Exception as exc:  # noqa: BLE001 — intentionally broad; Redis/RQ throw many subclasses
        logger.warning(
            "Enqueue failed for photo %s — Redis down? Photo accepted, AI pending. Error: %s",
            photo_id, exc,
        )
        job_id = None
        enqueue_status = "pending_enqueue"

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
            "enqueue_status": enqueue_status,
        },
    )
    db.add(audit)
    # session commit ผ่าน get_db() หลัง return

    return {
        "photo_id": str(photo_id),
        "job_id": job_id,
        "status": enqueue_status,
    }
