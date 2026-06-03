"""Security tests for POST /ingest/photos."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from joggy.db.session import get_db
from joggy.main import app
from joggy.middleware.event_token import EventTokenClaims


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


def _no_duplicate_result():
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    return result


@pytest.mark.asyncio
async def test_upload_rejects_spoofed_jpeg_magic_bytes(mock_db):
    """Content-Type alone is not enough; file bytes must match JPEG/PNG magic."""
    mock_db.execute.return_value = _no_duplicate_result()
    claims = EventTokenClaims(event_id=uuid.uuid4(), token_id=uuid.uuid4())

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db

    try:
        with (
            patch("joggy.api.ingest.verify_event_token", AsyncMock(return_value=claims)),
            patch("joggy.api.ingest.r2.upload_bytes") as upload_mock,
            patch("joggy.api.ingest.enqueue_process_photo", return_value="job-1"),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/ingest/photos?device_id=pi-001",
                    headers={"Authorization": "Bearer evt_test"},
                    files={"file": ("spoof.jpg", b"not really an image", "image/jpeg")},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 415
    upload_mock.assert_not_called()


@pytest.mark.asyncio
async def test_upload_rate_limits_by_event_token(mock_db):
    """Accepted uploads must be rate-limited per Event Token to contain leaked-token floods."""
    mock_db.execute.return_value = _no_duplicate_result()
    claims = EventTokenClaims(event_id=uuid.uuid4(), token_id=uuid.uuid4())
    rate_limit_mock = AsyncMock()

    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db

    try:
        with (
            patch("joggy.api.ingest.verify_event_token", AsyncMock(return_value=claims)),
            patch("joggy.api.ingest.check_rate_limit", rate_limit_mock, create=True),
            patch("joggy.api.ingest.r2.upload_bytes"),
            patch("joggy.api.ingest.enqueue_process_photo", return_value="job-1"),
        ):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                response = await client.post(
                    "/ingest/photos?device_id=pi-001",
                    headers={"Authorization": "Bearer evt_test"},
                    files={"file": ("photo.jpg", b"\xff\xd8\xff\xe0jpeg-bytes", "image/jpeg")},
                )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    rate_limit_mock.assert_awaited_once()
    call_kwargs = rate_limit_mock.call_args.kwargs
    assert call_kwargs["key_id"] == f"event-token:{claims.token_id}"
