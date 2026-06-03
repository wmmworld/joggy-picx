"""Security tests for internal Partner API key management."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from joggy.db.models import Organizer, PartnerApiKey
from joggy.db.session import get_db
from joggy.main import app
from joggy.middleware.internal_auth import InternalUserClaims, verify_internal_user


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    return db


def _staff_claims(organizer_id):
    return InternalUserClaims(
        user_id=uuid.uuid4(),
        role="staff",
        organizer_scope=[organizer_id],
        event_scope=[],
    )


@pytest.mark.asyncio
async def test_staff_cannot_issue_partner_api_key_even_with_organizer_scope(mock_db):
    """Partner API keys can grant external erasure scope, so issue must be admin-only."""
    organizer_id = uuid.uuid4()
    organizer_result = MagicMock()
    organizer_result.scalar_one_or_none.return_value = Organizer(
        id=organizer_id,
        name="Race Partner",
        contact_email="ops@example.com",
    )
    mock_db.execute.return_value = organizer_result

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[verify_internal_user] = lambda: _staff_claims(organizer_id)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                f"/internal/organizers/{organizer_id}/keys",
                json={"scopes": ["public:photos:read", "erasure:write"]},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_staff_cannot_revoke_partner_api_key_even_with_organizer_scope(mock_db):
    """Revoking external Partner API credentials is also admin-only."""
    organizer_id = uuid.uuid4()
    key_id = uuid.uuid4()
    key_result = MagicMock()
    key_result.scalar_one_or_none.return_value = PartnerApiKey(
        id=key_id,
        organizer_id=organizer_id,
        key_hash="argon2-hash",
        key_prefix="abcdef12",
        scopes=["public:photos:read"],
        issued_by_app_user_id=uuid.uuid4(),
    )
    mock_db.execute.return_value = key_result

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[verify_internal_user] = lambda: _staff_claims(organizer_id)

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.delete(
                f"/internal/organizers/{organizer_id}/keys/{key_id}"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403
    mock_db.add.assert_not_called()
