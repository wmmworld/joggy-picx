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
    
    # lookup event_tokens table โดย token_prefix (8 chars แรก)
    token_prefix = token[:8]
    
    stmt = select(EventToken).where(EventToken.token_prefix == token_prefix)
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
