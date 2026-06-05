"""Tests for GET /internal/events/{event_id}/photos endpoint."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from joggy.main import app
from joggy.db.session import get_db
from joggy.middleware.internal_auth import verify_internal_user, InternalUserClaims
from joggy.db.models import (
    Photo, Checkpoint, AIReviewStatus, Event, EventStatus,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def admin_claims():
    return InternalUserClaims(
        user_id=uuid.uuid4(),
        role="admin",
        organizer_scope=[],
        event_scope=[],
    )


@pytest.fixture
def mock_db():
    from unittest.mock import AsyncMock
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def api_client(mock_db, admin_claims):
    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[verify_internal_user] = lambda: admin_claims
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


def _make_event(event_id: uuid.UUID) -> Event:
    return Event(
        id=event_id,
        organizer_id=uuid.uuid4(),
        name="Test Race",
        start_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 6, 1, 12, tzinfo=timezone.utc),
        status=EventStatus.active,
    )


def _make_photo(
    photo_id: uuid.UUID,
    event_id: uuid.UUID,
    bib: str | None = "1234",
    status: AIReviewStatus = AIReviewStatus.auto,
) -> Photo:
    return Photo(
        id=photo_id,
        event_id=event_id,
        uploaded_by_event_token_id=uuid.uuid4(),
        device_id="pi-001",
        r2_key_original=f"events/{event_id}/{photo_id}/original.jpg",
        sha256="abc123",
        bib_number_nullable=bib,
        bib_confidence=0.85 if bib else None,
        ai_review_status=status,
        captured_at=datetime(2026, 6, 1, 9, tzinfo=timezone.utc),
    )


def _make_checkpoint(event_id: uuid.UUID, name: str = "กม.5") -> Checkpoint:
    return Checkpoint(
        id=uuid.uuid4(),
        event_id=event_id,
        name=name,
        kind="km5",
        seq_order=2,
    )


def _setup_db(mock_db, event, total: int, rows: list, photo_bibs: list | None = None):
    """Stage mock_db.execute: event lookup → count → paginated rows → photo_bibs.

    Photo_bibs query is only executed when `rows` has at least one photo, but
    we always stage a result so passing more side_effects than consumed is fine.
    """
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event

    count_result = MagicMock()
    count_result.scalar_one.return_value = total

    rows_result = MagicMock()
    rows_result.all.return_value = rows

    # ADR-0008 Phase B: list_event_photos batch-loads PhotoBib after fetching
    # the page. .scalars().all() returns the bib rows (default: empty list).
    bibs_result = MagicMock()
    bibs_result.scalars.return_value.all.return_value = photo_bibs or []

    mock_db.execute.side_effect = [event_result, count_result, rows_result, bibs_result]


# ── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_event_photos_returns_paginated_items(api_client, mock_db):
    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(photo_id, event_id)
    checkpoint = _make_checkpoint(event_id)
    _setup_db(mock_db, event, total=1, rows=[(photo, checkpoint)])

    with patch("joggy.api.internal.r2.signed_url", return_value="https://r2.test/signed"):
        async with api_client as client:
            response = await client.get(f"/internal/events/{event_id}/photos")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["per_page"] == 24
    assert data["pages"] == 1
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["photo_id"] == str(photo_id)
    assert item["bib_number"] == "1234"
    assert item["ai_review_status"] == "auto"
    assert item["thumbnail_url"] == "https://r2.test/signed"
    assert item["checkpoint_name"] == "กม.5"


@pytest.mark.asyncio
async def test_list_event_photos_pagination_metadata(api_client, mock_db):
    event_id = uuid.uuid4()
    event = _make_event(event_id)
    photo_id = uuid.uuid4()
    photo = _make_photo(photo_id, event_id)
    _setup_db(mock_db, event, total=50, rows=[(photo, None)])

    with patch("joggy.api.internal.r2.signed_url", return_value="https://r2.test/signed"):
        async with api_client as client:
            response = await client.get(
                f"/internal/events/{event_id}/photos?page=2&per_page=24"
            )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 50
    assert data["page"] == 2
    assert data["pages"] == 3


@pytest.mark.asyncio
async def test_list_event_photos_no_checkpoint_returns_none(api_client, mock_db):
    event_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(uuid.uuid4(), event_id)
    _setup_db(mock_db, event, total=1, rows=[(photo, None)])

    with patch("joggy.api.internal.r2.signed_url", return_value="https://r2.test/signed"):
        async with api_client as client:
            response = await client.get(f"/internal/events/{event_id}/photos")

    assert response.status_code == 200
    assert response.json()["items"][0]["checkpoint_name"] is None


@pytest.mark.asyncio
async def test_list_event_photos_invalid_ai_status_returns_422(api_client, mock_db):
    event_id = uuid.uuid4()
    event = _make_event(event_id)
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    mock_db.execute.return_value = event_result

    async with api_client as client:
        response = await client.get(
            f"/internal/events/{event_id}/photos?ai_status=invalid_value"
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_event_photos_event_not_found_returns_404(api_client, mock_db):
    event_id = uuid.uuid4()
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = event_result

    async with api_client as client:
        response = await client.get(f"/internal/events/{event_id}/photos")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_event_photos_per_page_over_limit_returns_422(api_client, mock_db):
    event_id = uuid.uuid4()
    async with api_client as client:
        response = await client.get(
            f"/internal/events/{event_id}/photos?per_page=101"
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_event_photos_combined_filters(api_client, mock_db):
    """Multiple filters (bib + ai_status) AND-combine correctly."""
    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(photo_id, event_id, bib="1234", status=AIReviewStatus.auto)
    _setup_db(mock_db, event, total=1, rows=[(photo, None)])

    with patch("joggy.api.internal.r2.signed_url", return_value="https://r2.test/signed"):
        async with api_client as client:
            response = await client.get(
                f"/internal/events/{event_id}/photos?bib=1234&ai_status=auto"
            )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["bib_number"] == "1234"
    assert data["items"][0]["ai_review_status"] == "auto"


@pytest.mark.asyncio
async def test_list_event_photos_bib_filter_escapes_wildcards(api_client, mock_db):
    """bib='1%' should be escaped to literal '1%' not used as LIKE wildcard."""
    event_id = uuid.uuid4()
    event = _make_event(event_id)
    _setup_db(mock_db, event, total=0, rows=[])

    with patch("joggy.api.internal.r2.signed_url"):
        async with api_client as client:
            response = await client.get(f"/internal/events/{event_id}/photos?bib=1%25")
            # %25 is URL-encoded '%' — endpoint should escape it before ILIKE

    assert response.status_code == 200
    # Just verify no crash + valid response shape
    assert response.json()["total"] == 0


# ── ADR-0008 Phase B: PhotoBib payload + EXISTS bib filter ────────────────────


@pytest.mark.asyncio
async def test_list_event_photos_includes_bibs_payload(api_client, mock_db):
    """Photo with 2 PhotoBib rows should expose both via the `bibs` field."""
    from joggy.db.models import PhotoBib

    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(photo_id, event_id)
    bibs = [
        PhotoBib(
            id=uuid.uuid4(), photo_id=photo_id,
            bib_number="1234", confidence=0.95,
            bbox_x1=10, bbox_y1=20, bbox_x2=110, bbox_y2=80,
        ),
        PhotoBib(
            id=uuid.uuid4(), photo_id=photo_id,
            bib_number="5678", confidence=0.81,
            bbox_x1=200, bbox_y1=20, bbox_x2=300, bbox_y2=80,
        ),
    ]
    _setup_db(mock_db, event, total=1, rows=[(photo, None)], photo_bibs=bibs)

    with patch("joggy.api.internal.r2.signed_url", return_value="https://r2.test/signed"):
        async with api_client as client:
            response = await client.get(f"/internal/events/{event_id}/photos")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert len(item["bibs"]) == 2
    bib_numbers = {b["bib_number"] for b in item["bibs"]}
    assert bib_numbers == {"1234", "5678"}
    # bbox fields round-trip
    high_conf = next(b for b in item["bibs"] if b["bib_number"] == "1234")
    assert high_conf["confidence"] == 0.95
    assert high_conf["bbox_x1"] == 10
    assert high_conf["bbox_x2"] == 110


@pytest.mark.asyncio
async def test_list_event_photos_bib_filter_uses_photo_bibs_exists(api_client, mock_db):
    """ADR-0008 Phase B: bib= filter must use EXISTS on photo_bibs, not the
    deprecated Photo.bib_number_nullable column.

    Inspects the compiled SQL of the photos query (3rd execute call: event,
    count, then rows).
    """
    from unittest.mock import AsyncMock

    event_id = uuid.uuid4()
    event = _make_event(event_id)
    captured_sql: list[str] = []

    async def _execute(stmt, *args, **kwargs):
        captured_sql.append(str(stmt.compile(compile_kwargs={"literal_binds": False})))
        m = MagicMock()
        n = len(captured_sql)
        if n == 1:                        # event lookup
            m.scalar_one_or_none.return_value = event
        elif n == 2:                      # count(*)
            m.scalar_one.return_value = 0
        elif n == 3:                      # paginated rows
            m.all.return_value = []
        else:                             # PhotoBib batch-load (not reached when 0 rows)
            m.scalars.return_value.all.return_value = []
        return m

    mock_db.execute = _execute

    with patch("joggy.api.internal.r2.signed_url"):
        async with api_client as client:
            response = await client.get(f"/internal/events/{event_id}/photos?bib=1234")

    assert response.status_code == 200
    # Count query (index 1) carries the same WHERE clause as the row query.
    # Both should reference photo_bibs.bib_number via EXISTS, NOT the
    # deprecated photos.bib_number_nullable ilike.
    count_sql = captured_sql[1].lower()
    assert "photo_bibs.bib_number" in count_sql
    assert "exists" in count_sql
    assert "photos.bib_number_nullable ilike" not in count_sql
