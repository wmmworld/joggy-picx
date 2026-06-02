import uuid
from datetime import datetime, timezone
import argon2
from fastapi import Depends, HTTPException, Response, status
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List

from joggy.db.models import PartnerApiKey
from joggy.db.session import get_db
from joggy.middleware.rate_limit import check_rate_limit

class PartnerKeyClaims(BaseModel):
    organizer_id: uuid.UUID
    key_id: uuid.UUID
    scopes: List[str]

api_key_header = APIKeyHeader(name="X-API-Key")
ph = argon2.PasswordHasher()

async def verify_partner_api_key(
    response: Response,
    api_key: str = Depends(api_key_header),
    db: AsyncSession = Depends(get_db),
) -> PartnerKeyClaims:
    """
    FastAPI Dependency สำหรับตรวจสอบ Partner API Key
    ดึง key จาก Header: X-API-Key
    """
    if len(api_key) < 8:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid API key format"
        )
        
    # lookup partner_api_keys table โดย key_prefix
    key_prefix = api_key[:8]
    
    stmt = select(PartnerApiKey).where(PartnerApiKey.key_prefix == key_prefix)
    result = await db.execute(stmt)
    partner_key = result.scalar_one_or_none()
    
    if not partner_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="API key not found"
        )
        
    # ตรวจ revoked_at
    if partner_key.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="API key has been revoked"
        )
        
    # argon2 verify
    try:
        ph.verify(partner_key.key_hash, api_key)
    except argon2.exceptions.VerifyMismatchError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid API key"
        )
        
    # Rate limit check (raises 429 if over limit; sets X-RateLimit-* headers)
    await check_rate_limit(
        key_id=str(partner_key.id),
        limit_per_minute=partner_key.rate_limit_per_minute,
        response=response,
    )

    # อัปเดต last_used_at — ใช้ Python datetime (ไม่ใช่ SQL func.now() ซึ่งเป็น expression)
    partner_key.last_used_at = datetime.now(timezone.utc)
    db.add(partner_key)
    # ไม่ commit ที่นี่ — session จะ commit เมื่อ request handler เสร็จผ่าน get_db()
    
    return PartnerKeyClaims(
        organizer_id=partner_key.organizer_id,
        key_id=partner_key.id,
        scopes=partner_key.scopes
    )
