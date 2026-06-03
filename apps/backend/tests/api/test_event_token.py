"""Tests for POST /internal/events/{event_id}/tokens — Event Token generation."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from joggy.main import app
from joggy.db.session import get_db
from joggy.middleware.internal_auth import verify_internal_user, InternalUserClaims
from joggy.db.models import Event, EventStatus


def _make_admin_claims():
    return InternalUserClaims(
        user_id=uuid.uuid4(),
        role="admin",
        organizer_scope=[],
        event_scope=[],
    )


def _make_staff_claims():
    return InternalUserClaims(
        user_id=uuid.uuid4(),
        role="staff",
        organizer_scope=[],
        event_scope=[],
    )


def _make_event(event_id: uuid.UUID) -> Event:
    return Event(
        id=event_id,
        organizer_id=uuid.uuid4(),
        name="Test Race",
        start_at=datetime(2026, 6, 1),
        end_at=datetime(2026, 12, 31),
        status=EventStatus.active,
    )


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_admin_can_issue_event_token(mock_db):
    """Happy path — admin issues token, gets plaintext + prefix back."""
    event_id = uuid.uuid4()
    event = _make_event(event_id)

    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    mock_db.execute.return_value = event_result

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[verify_internal_user] = lambda: _make_admin_claims()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/internal/events/{event_id}/tokens")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    data = response.json()
    assert data["plaintext_token"].startswith("evt_")
    # L-002 from security audit 2026-06-03: prefix bumped from 8 to 12 chars
    # (4 "evt_" + 8 random) to reduce display/lookup collision risk
    assert data["token_prefix"] == data["plaintext_token"][:12]
    assert len(data["token_prefix"]) == 12
    assert data["event_id"] == str(event_id)
    assert data["event_name"] == "Test Race"
    assert "token_id" in data
    assert "expires_at" in data


@pytest.mark.asyncio
async def test_staff_cannot_issue_event_token(mock_db):
    """Non-admin gets 403."""
    event_id = uuid.uuid4()

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[verify_internal_user] = lambda: _make_staff_claims()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/internal/events/{event_id}/tokens")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_event_not_found_returns_404(mock_db):
    """Non-existent event_id → 404."""
    event_id = uuid.uuid4()

    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = event_result

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[verify_internal_user] = lambda: _make_admin_claims()

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(f"/internal/events/{event_id}/tokens")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
