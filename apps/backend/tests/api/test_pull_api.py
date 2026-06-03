"""Integration tests for race-result.asia Pull API (GET /v1/public/photos)."""
import uuid
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from joggy.main import app
from joggy.db.session import get_db
from joggy.middleware.partner_key import verify_partner_api_key, PartnerKeyClaims
from joggy.db.models import AIReviewStatus, Photo, Checkpoint, Event, EventStatus
from datetime import datetime, timezone


def _make_partner_claims(scopes=None, organizer_id=None):
    return PartnerKeyClaims(
        organizer_id=organizer_id or uuid.uuid4(),
        key_id=uuid.uuid4(),
        scopes=scopes if scopes is not None else ["public:photos:read"],
    )


def _make_photo(event_id, bib="1234"):
    return Photo(
        id=uuid.uuid4(),
        event_id=event_id,
        uploaded_by_event_token_id=uuid.uuid4(),
        device_id="pi-001",
        r2_key_original=f"events/{event_id}/orig.jpg",
        r2_key_thumbnail=f"events/{event_id}/thumb.jpg",
        sha256="abc123",
        bib_number_nullable=bib,
        ai_review_status=AIReviewStatus.auto,
        captured_at=datetime(2026, 6, 1, 9, tzinfo=timezone.utc),
    )


def _make_event(event_id, organizer_id):
    return Event(
        id=event_id,
        organizer_id=organizer_id,
        name="Test Race",
        start_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 6, 1, 12, tzinfo=timezone.utc),
        status=EventStatus.active,
    )


def _setup_event_and_rows(mock_db, event, rows):
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    rows_result = MagicMock()
    rows_result.all.return_value = rows
    mock_db.execute.side_effect = [event_result, rows_result]


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def partner_claims():
    return _make_partner_claims()


@pytest.fixture
def api_client(mock_db, partner_claims):
    """Test client with mocked DB and partner auth."""
    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[verify_partner_api_key] = lambda: partner_claims
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


# ── Tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_happy_path_returns_photos_with_urls(api_client, mock_db, partner_claims):
    """Valid request with matching photos returns correct response shape."""
    event_id = uuid.uuid4()
    photo = _make_photo(event_id, bib="1234")
    event = _make_event(event_id, partner_claims.organizer_id)
    _setup_event_and_rows(mock_db, event, [(photo, None)])

    with patch("joggy.api.public.signed_url", return_value="https://r2.example/signed"):
        async with api_client as client:
            response = await client.get(
                f"/v1/public/photos?event_id={event_id}&bib=1234"
            )

    assert response.status_code == 200
    data = response.json()
    assert data["bib"] == "1234"
    assert data["event_id"] == str(event_id)
    assert len(data["photos"]) == 1
    photo_item = data["photos"][0]
    assert "photo_id" in photo_item
    assert "original_url" in photo_item
    assert photo_item["original_url"] == "https://r2.example/signed"


@pytest.mark.asyncio
async def test_no_matching_photos_returns_empty_list(api_client, mock_db, partner_claims):
    """When no photos match the bib, returns 200 with empty photos list."""
    event_id = uuid.uuid4()
    event = _make_event(event_id, partner_claims.organizer_id)
    _setup_event_and_rows(mock_db, event, [])

    with patch("joggy.api.public.signed_url", return_value="https://r2.example/signed"):
        async with api_client as client:
            response = await client.get(
                f"/v1/public/photos?event_id={event_id}&bib=9999"
            )

    assert response.status_code == 200
    data = response.json()
    assert data["photos"] == []
    assert data["bib"] == "9999"


@pytest.mark.asyncio
async def test_missing_api_key_returns_401():
    """No X-API-Key header → 401 Unauthorized."""
    # Don't use the fixture that overrides auth — test real auth dependency
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/v1/public/photos?event_id=00000000-0000-0000-0000-000000000001&bib=1234"
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_wrong_scope_returns_403(mock_db):
    """Key with wrong scopes → 403 Forbidden."""
    event_id = uuid.uuid4()
    claims_no_scope = _make_partner_claims(scopes=["other:scope"])

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[verify_partner_api_key] = lambda: claims_no_scope

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/v1/public/photos?event_id={event_id}&bib=1234"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_partner_cannot_read_photos_for_other_organizer(mock_db):
    """Cross-organizer event_id must be rejected before returning signed URLs."""
    event_id = uuid.uuid4()
    partner_organizer_id = uuid.uuid4()
    other_organizer_id = uuid.uuid4()
    claims = _make_partner_claims(organizer_id=partner_organizer_id)
    event = Event(
        id=event_id,
        organizer_id=other_organizer_id,
        name="Other Organizer Race",
        start_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 6, 1, 12, tzinfo=timezone.utc),
        status=EventStatus.active,
    )

    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    rows_result = MagicMock()
    rows_result.all.return_value = []
    mock_db.execute.side_effect = [event_result, rows_result]

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[verify_partner_api_key] = lambda: claims

    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                f"/v1/public/photos?event_id={event_id}&bib=1234"
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_response_includes_security_headers(api_client, mock_db, partner_claims):
    """Security headers middleware active on public endpoints."""
    event_id = uuid.uuid4()
    event = _make_event(event_id, partner_claims.organizer_id)
    _setup_event_and_rows(mock_db, event, [])

    with patch("joggy.api.public.signed_url", return_value="https://r2.example/signed"):
        async with api_client as client:
            response = await client.get(
                f"/v1/public/photos?event_id={event_id}&bib=1234"
            )

    assert response.status_code == 200
    # Security headers injected by SecurityHeadersMiddleware
    assert "X-Frame-Options" in response.headers
    assert response.headers["X-Frame-Options"] == "DENY"
    assert "X-Content-Type-Options" in response.headers
    # Rate limit headers injected by check_rate_limit (fail-open if Redis absent)
    # If Redis is running: X-RateLimit-Limit present. If not: absent (fail-open).
    # Just check the response came back successfully — don't assert rate limit
    # headers since they depend on Redis availability in test environment.


# ── M-001 from security audit 2026-06-03 — typed UUID + bib validation ─────────

@pytest.mark.asyncio
async def test_invalid_event_id_returns_422(api_client):
    """Malformed event_id is rejected by FastAPI before reaching the handler."""
    async with api_client as client:
        response = await client.get("/v1/public/photos?event_id=not-a-uuid&bib=1234")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_bib_with_special_chars_returns_422(api_client):
    """Bib with disallowed characters (e.g., SQL/path injection attempts) → 422."""
    async with api_client as client:
        response = await client.get(
            f"/v1/public/photos?event_id={uuid.uuid4()}&bib=' OR 1=1--"
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_bib_too_long_returns_422(api_client):
    """Bib exceeding max_length=20 → 422."""
    async with api_client as client:
        response = await client.get(
            f"/v1/public/photos?event_id={uuid.uuid4()}&bib={'1' * 21}"
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_empty_bib_returns_422(api_client):
    """Empty bib (min_length=1 violation) → 422."""
    async with api_client as client:
        response = await client.get(
            f"/v1/public/photos?event_id={uuid.uuid4()}&bib="
        )
    assert response.status_code == 422

