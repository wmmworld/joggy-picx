import uuid
from datetime import datetime, timezone
import argon2
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from joggy.db.models import EventToken
from joggy.db.session import get_db

class EventTokenClaims(BaseModel):
    event_id: uuid.UUID
    token_id: uuid.UUID

security = HTTPBearer()
ph = argon2.PasswordHasher()

async def verify_event_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> EventTokenClaims:
    """
    FastAPI Dependency สำหรับตรวจสอบ Per-Event Upload Token
    ดึง token จาก Authorization: Bearer evt_xxxxx
    """
    token = credentials.credentials
    if not token.startswith("evt_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid token format"
        )
    
    # L-002 from security audit 2026-06-03: token_prefix now 12 chars
    # (4 prefix "evt_" + 8 random) instead of 4 random chars. Lower collision.
    # Backward-compat: try new 12-char prefix first; fall back to legacy 8-char.
    # Remove fallback after all pre-2026-06-04 tokens have expired.
    prefix_new = token[:12]
    prefix_legacy = token[:8]

    stmt = select(EventToken).where(EventToken.token_prefix == prefix_new)
    result = await db.execute(stmt)
    event_token = result.scalar_one_or_none()

    if event_token is None:
        # Legacy lookup for tokens issued before 2026-06-04
        stmt = select(EventToken).where(EventToken.token_prefix == prefix_legacy)
        result = await db.execute(stmt)
        event_token = result.scalar_one_or_none()

    if not event_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token not found"
        )
        
    # ตรวจ revoked_at IS NULL
    if event_token.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Token has been revoked"
        )
        
    # ตรวจ expires_at > now()
    now = datetime.now(timezone.utc)
    expires_at = event_token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Token has expired"
        )
        
    # argon2 verify token กับ token_hash
    try:
        ph.verify(event_token.token_hash, token)
    except argon2.exceptions.VerifyMismatchError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid token"
        )
        
    return EventTokenClaims(event_id=event_token.event_id, token_id=event_token.id)
