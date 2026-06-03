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

    # Claude (2026-05-31): Supabase ใช้ HS256 symmetric secret โดย default
    # JWT secret หาได้ที่ Supabase Dashboard → Settings → API → JWT Secret
    # ถ้า project ใหม่ใช้ asymmetric (RS256) ค่อย fallback ไป JWKS
    payload = None
    last_error: Exception | None = None
    # Codex: Supabase JWT ต้องผูกกับ project issuer เดียวกับ SUPABASE_URL ไม่ใช่แค่ signature/audience
    expected_issuer = f"{settings.supabase_url.rstrip('/')}/auth/v1"
    required_claims = {"require": ["sub", "aud", "iss", "exp"]}

    # Try 1: HS256 with jwt_secret (Supabase default)
    if settings.supabase_jwt_secret:
        try:
            payload = jwt.decode(
                token,
                settings.supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
                issuer=expected_issuer,
                options=required_claims,
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            )
        except (jwt.InvalidIssuerError, jwt.InvalidAudienceError, jwt.MissingRequiredClaimError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        except Exception as e:
            last_error = e  # fall through to RS256 attempt

    # Try 2: Asymmetric via JWKS — ES256 (new Supabase) or RS256 (older)
    rs256_error: Exception | None = None
    if payload is None:
        try:
            jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
            jwks_client = jwt.PyJWKClient(jwks_url, cache_keys=True)
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256"],
                audience="authenticated",
                issuer=expected_issuer,
                options=required_claims,
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            )
        except (jwt.InvalidIssuerError, jwt.InvalidAudienceError, jwt.MissingRequiredClaimError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        except Exception as e:
            rs256_error = e

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
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
