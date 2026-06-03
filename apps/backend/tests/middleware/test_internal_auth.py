"""Security tests for Supabase internal JWT verification."""
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from joggy.db.models import AppUser, UserRole
from joggy.middleware.internal_auth import verify_internal_user


def _execute_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    result.scalars.return_value.all.return_value = []
    return result


@pytest.mark.asyncio
async def test_internal_jwt_rejects_wrong_issuer():
    """A signed Supabase JWT must still match this project's issuer."""
    secret = "test-secret"
    user_id = uuid.uuid4()
    token = jwt.encode(
        {
            "sub": str(user_id),
            "aud": "authenticated",
            "iss": "https://evil.example/auth/v1",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        secret,
        algorithm="HS256",
    )
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    db = AsyncMock()
    db.execute.side_effect = [
        _execute_result(AppUser(
            id=user_id,
            role=UserRole.admin,
            display_name="Admin",
            mfa_enrolled=True,
        )),
        _execute_result(None),
        _execute_result(None),
    ]
    settings = SimpleNamespace(
        supabase_jwt_secret=secret,
        supabase_url="https://project.supabase.co",
    )

    with patch("joggy.middleware.internal_auth.get_settings", return_value=settings):
        with pytest.raises(HTTPException) as exc_info:
            await verify_internal_user(credentials=credentials, db=db)

    assert exc_info.value.status_code == 401
