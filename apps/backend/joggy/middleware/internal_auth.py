import uuid
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List

from joggy.core.config import get_settings
from joggy.db.models import AppUser, AppUserOrganizerScope, AppUserEventScope
from joggy.db.session import get_db

class InternalUserClaims(BaseModel):
    user_id: uuid.UUID
    role: str
    organizer_scope: List[uuid.UUID]
    event_scope: List[uuid.UUID]

security = HTTPBearer()

async def verify_internal_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> InternalUserClaims:
    """
    FastAPI Dependency สำหรับตรวจสอบ Internal User (Supabase Auth)
    """
    token = credentials.credentials
    
    settings = get_settings()
    try:
        # Verify Supabase JWT ด้วย JWKS จาก SUPABASE_URL (รองรับ RS256)
        # Supabase ใช้ JWT secret แบบ symmetric (HS256) — ดึงจาก Project Settings → API → JWT Secret
        # ใช้ SUPABASE_SERVICE_ROLE_KEY เป็น signing secret (Supabase ใช้ HS256 ด้วย jwt_secret)
        jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
        jwks_client = jwt.PyJWKClient(jwks_url, cache_keys=True)
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "HS256"],
            audience="authenticated",
        )
        # ห้ามมี dev fallback ที่ verify_signature=False — ถ้า Supabase URL ไม่ถูกต้อง ให้ fail loud
            
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Token expired"
        )
    except Exception as e:
        # ห้าม log token หรือรายละเอียด error ออกไปที่ผู้ใช้
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid token"
        )

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid token payload"
        )
        
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid user_id format"
        )

    # lookup app_users table
    stmt = select(AppUser).where(AppUser.id == user_id)
    result = await db.execute(stmt)
    app_user = result.scalar_one_or_none()
    
    if not app_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="User not found in app_users"
        )
        
    # ตรวจ mfa_enrolled = true
    if not app_user.mfa_enrolled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="MFA is required but not enrolled"
        )

    # ดึง organizer scope
    org_stmt = select(AppUserOrganizerScope.organizer_id).where(AppUserOrganizerScope.app_user_id == user_id)
    org_result = await db.execute(org_stmt)
    organizer_scope = list(org_result.scalars().all())
    
    # ดึง event scope
    event_stmt = select(AppUserEventScope.event_id).where(AppUserEventScope.app_user_id == user_id)
    event_result = await db.execute(event_stmt)
    event_scope = list(event_result.scalars().all())
    
    return InternalUserClaims(
        user_id=user_id,
        role=app_user.role,
        organizer_scope=organizer_scope,
        event_scope=event_scope
    )
