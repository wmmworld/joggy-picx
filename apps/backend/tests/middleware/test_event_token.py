"""Tests for verify_event_token middleware — L-002 prefix backward-compat."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import argon2
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from joggy.db.models import EventToken
from joggy.middleware.event_token import verify_event_token


_ph = argon2.PasswordHasher()


def _make_event_token(prefix_len: int, plaintext: str | None = None) -> tuple[EventToken, str]:
    """Build an EventToken row with `prefix_len` chars stored as token_prefix.

    Used to simulate legacy (8-char) tokens vs new (12-char) tokens.
    """
    plaintext = plaintext or f"evt_{uuid.uuid4().hex}"
    et = EventToken(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        token_hash=_ph.hash(plaintext),
        token_prefix=plaintext[:prefix_len],
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        issued_by_app_user_id=uuid.uuid4(),
    )
    return et, plaintext


def _make_db(returns: list[EventToken | None]) -> AsyncMock:
    """Build an AsyncMock db where each .execute() returns one of `returns`."""
    db = AsyncMock()
    side_effects = []
    for ret in returns:
        result = MagicMock()
        result.scalar_one_or_none.return_value = ret
        side_effects.append(result)
    db.execute = AsyncMock(side_effect=side_effects)
    return db


@pytest.mark.asyncio
async def test_verify_with_new_12char_prefix():
    """New tokens issued post-L-002 use 12-char prefix; lookup hits on first try."""
    et, plaintext = _make_event_token(prefix_len=12)
    db = _make_db([et])
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=plaintext)

    claims = await verify_event_token(credentials=creds, db=db)

    assert claims.token_id == et.id
    assert claims.event_id == et.event_id
    # Only first lookup (12-char) was needed
    assert db.execute.call_count == 1


@pytest.mark.asyncio
async def test_verify_with_legacy_8char_prefix_falls_back():
    """Tokens issued before L-002 still work via fallback lookup (backward compat)."""
    et, plaintext = _make_event_token(prefix_len=8)
    # First execute (12-char lookup) returns None; second (8-char) returns the row
    db = _make_db([None, et])
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=plaintext)

    claims = await verify_event_token(credentials=creds, db=db)

    assert claims.token_id == et.id
    # Both lookups attempted
    assert db.execute.call_count == 2


@pytest.mark.asyncio
async def test_verify_rejects_unknown_token():
    """Token whose prefix matches neither 12 nor 8-char column → 401."""
    db = _make_db([None, None])
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="evt_unknownXYZ")

    with pytest.raises(HTTPException) as exc:
        await verify_event_token(credentials=creds, db=db)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_rejects_bad_format():
    """Token missing 'evt_' prefix → 401 immediately (no DB lookup)."""
    db = AsyncMock()
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="not_a_token")

    with pytest.raises(HTTPException) as exc:
        await verify_event_token(credentials=creds, db=db)
    assert exc.value.status_code == 401
    db.execute.assert_not_called()
