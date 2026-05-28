import secrets
import uuid
import argon2
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from joggy.db.models import EventToken, Event

ph = argon2.PasswordHasher()

async def generate_event_token(
    event_id: uuid.UUID,
    issued_by: uuid.UUID,
    db: AsyncSession
) -> tuple[str, EventToken]:
    """
    สร้าง Per-Event Upload Token (D-017)
    return (plaintext_token, EventToken object)
    
    คำเตือน: ต้องส่ง plaintext_token ให้ผู้เรียกเพียงครั้งเดียว และห้าม log เด็ดขาด
    """
    stmt = select(Event).where(Event.id == event_id)
    result = await db.execute(stmt)
    event = result.scalar_one_or_none()
    
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Event not found"
        )
        
    plaintext_token = f"evt_{secrets.token_urlsafe(32)}"
    token_prefix = plaintext_token[:8]
    token_hash = ph.hash(plaintext_token)
    
    event_token = EventToken(
        event_id=event_id,
        token_hash=token_hash,
        token_prefix=token_prefix,
        expires_at=event.end_at,
        issued_by_app_user_id=issued_by
    )
    
    db.add(event_token)
    await db.commit()
    await db.refresh(event_token)
    
    return plaintext_token, event_token
