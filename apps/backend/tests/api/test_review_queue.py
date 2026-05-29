"""Tests for GET/PATCH /internal/review-queue endpoints."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport

from joggy.main import app
from joggy.db.session import get_db
from joggy.middleware.internal_auth import verify_internal_user, InternalUserClaims
from joggy.db.models import (
    ReviewQueue, ReviewQueueStatus, Photo, Checkpoint,
    AIReviewStatus, Event, EventStatus,
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
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def api_client(mock_db, admin_claims):
    """FastAPI test client with mocked auth + DB."""
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


def _make_photo(photo_id: uuid.UUID, event_id: uuid.UUID) -> Photo:
    return Photo(
        id=photo_id,
        event_id=event_id,
        uploaded_by_event_token_id=uuid.uuid4(),
        device_id="pi-001",
        r2_key_original=f"events/{event_id}/{photo_id}/original.jpg",
        sha256="abc123",
        bib_number_nullable="1234",
        bib_confidence=0.52,
        ai_review_status=AIReviewStatus.manual_pending,
    )


def _make_queue_item(photo_id: uuid.UUID) -> ReviewQueue:
    return ReviewQueue(
        id=uuid.uuid4(),
        photo_id=photo_id,
        reason="low_ocr_conf",
        status=ReviewQueueStatus.pending,
        created_at=datetime(2026, 6, 1, 10, tzinfo=timezone.utc),
    )


def _make_checkpoint(event_id: uuid.UUID) -> Checkpoint:
    return Checkpoint(
        id=uuid.uuid4(),
        event_id=event_id,
        name="กม.5",
        kind="km5",
        seq_order=2,
    )


# ── GET /internal/review-queue tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_review_queue_returns_pending_items(api_client, mock_db):
    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(photo_id, event_id)
    rq = _make_queue_item(photo_id)
    checkpoint = _make_checkpoint(event_id)

    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    rows_result = MagicMock()
    rows_result.all.return_value = [(rq, photo, checkpoint)]
    mock_db.execute.side_effect = [event_result, rows_result]

    with patch("joggy.api.internal.r2.signed_url", return_value="https://r2.test/signed"):
        async with api_client as client:
            response = await client.get(f"/internal/review-queue?event_id={event_id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    item = data[0]
    assert item["queue_id"] == str(rq.id)
    assert item["photo_id"] == str(photo_id)
    assert item["reason"] == "low_ocr_conf"
    assert item["bib_number"] == "1234"
    assert item["bib_confidence"] == pytest.approx(0.52)
    assert item["thumbnail_url"] == "https://r2.test/signed"
    assert item["checkpoint_name"] == "กม.5"


@pytest.mark.asyncio
async def test_list_review_queue_returns_empty_when_no_items(api_client, mock_db):
    event_id = uuid.uuid4()
    event = _make_event(event_id)

    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    rows_result = MagicMock()
    rows_result.all.return_value = []
    mock_db.execute.side_effect = [event_result, rows_result]

    with patch("joggy.api.internal.r2.signed_url", return_value="https://r2.test/signed"):
        async with api_client as client:
            response = await client.get(f"/internal/review-queue?event_id={event_id}")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_review_queue_404_when_event_not_found(api_client, mock_db):
    event_id = uuid.uuid4()
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = event_result

    async with api_client as client:
        response = await client.get(f"/internal/review-queue?event_id={event_id}")

    assert response.status_code == 404


# ── PATCH /internal/review-queue/{queue_id} tests ───────────────────────────

@pytest.mark.asyncio
async def test_approve_sets_manual_approved_status(api_client, mock_db):
    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    queue_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(photo_id, event_id)
    rq = _make_queue_item(photo_id)
    rq.id = queue_id

    rq_result = MagicMock()
    rq_result.scalar_one_or_none.return_value = rq
    photo_result = MagicMock()
    photo_result.scalar_one_or_none.return_value = photo
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    mock_db.execute.side_effect = [rq_result, photo_result, event_result]

    async with api_client as client:
        response = await client.patch(
            f"/internal/review-queue/{queue_id}",
            json={"action": "approve"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert photo.ai_review_status == AIReviewStatus.manual_approved
    assert rq.status == ReviewQueueStatus.approved
    assert rq.resolved_at is not None


@pytest.mark.asyncio
async def test_approve_with_override_bib_updates_photo(api_client, mock_db):
    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    queue_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(photo_id, event_id)
    rq = _make_queue_item(photo_id)
    rq.id = queue_id

    rq_result = MagicMock()
    rq_result.scalar_one_or_none.return_value = rq
    photo_result = MagicMock()
    photo_result.scalar_one_or_none.return_value = photo
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    mock_db.execute.side_effect = [rq_result, photo_result, event_result]

    async with api_client as client:
        response = await client.patch(
            f"/internal/review-queue/{queue_id}",
            json={"action": "approve", "decision_bib": "9999"},
        )

    assert response.status_code == 200
    assert photo.bib_number_nullable == "9999"
    assert rq.decision_bib == "9999"


@pytest.mark.asyncio
async def test_reject_sets_manual_rejected_status(api_client, mock_db):
    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    queue_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(photo_id, event_id)
    rq = _make_queue_item(photo_id)
    rq.id = queue_id

    rq_result = MagicMock()
    rq_result.scalar_one_or_none.return_value = rq
    photo_result = MagicMock()
    photo_result.scalar_one_or_none.return_value = photo
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    mock_db.execute.side_effect = [rq_result, photo_result, event_result]

    async with api_client as client:
        response = await client.patch(
            f"/internal/review-queue/{queue_id}",
            json={"action": "reject"},
        )

    assert response.status_code == 200
    assert photo.ai_review_status == AIReviewStatus.manual_rejected
    assert rq.status == ReviewQueueStatus.rejected


@pytest.mark.asyncio
async def test_patch_already_resolved_returns_409(api_client, mock_db):
    queue_id = uuid.uuid4()
    rq = _make_queue_item(uuid.uuid4())
    rq.id = queue_id
    rq.status = ReviewQueueStatus.approved  # already resolved

    rq_result = MagicMock()
    rq_result.scalar_one_or_none.return_value = rq
    mock_db.execute.return_value = rq_result

    async with api_client as client:
        response = await client.patch(
            f"/internal/review-queue/{queue_id}",
            json={"action": "approve"},
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_patch_not_found_returns_404(api_client, mock_db):
    queue_id = uuid.uuid4()
    rq_result = MagicMock()
    rq_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = rq_result

    async with api_client as client:
        response = await client.patch(
            f"/internal/review-queue/{queue_id}",
            json={"action": "approve"},
        )

    assert response.status_code == 404
