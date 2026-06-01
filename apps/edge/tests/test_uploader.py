"""Tests for uploader.upload_file() — happy path + response handling."""
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from joggy_edge.config import EdgeSettings
from joggy_edge.uploader import UploadOutcome, UploadResult, upload_file


@pytest.fixture
def settings(monkeypatch):
    monkeypatch.setenv("INGEST_URL", "https://vps.example/ingest/photos")
    monkeypatch.setenv("EVENT_TOKEN", "evt_test_token")
    return EdgeSettings(_env_file=None)  # type: ignore[call-arg]


@pytest.fixture
def jpeg_file(tmp_path: Path) -> Path:
    p = tmp_path / "test.jpg"
    p.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg-bytes")  # JPEG SOI + EXIF marker
    return p


def _mock_response(status: int, json_body: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status,
        json=json_body if json_body is not None else {},
        request=httpx.Request("POST", "https://vps.example/ingest/photos"),
    )


@pytest.mark.asyncio
async def test_upload_202_returns_uploaded(jpeg_file, settings):
    mock_response = _mock_response(202, {"photo_id": "uuid-1", "job_id": "job-1", "status": "queued"})
    with patch("joggy_edge.uploader.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        result = await upload_file(jpeg_file, settings)
    assert result.outcome == UploadOutcome.UPLOADED
    assert result.photo_id == "uuid-1"
    assert result.job_id == "job-1"


@pytest.mark.asyncio
async def test_upload_409_returns_duplicate(jpeg_file, settings):
    mock_response = _mock_response(409, {"detail": "duplicate sha256"})
    with patch("joggy_edge.uploader.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        result = await upload_file(jpeg_file, settings)
    assert result.outcome == UploadOutcome.DUPLICATE


@pytest.mark.asyncio
async def test_upload_413_returns_rejected(jpeg_file, settings):
    mock_response = _mock_response(413, {"detail": "too large"})
    with patch("joggy_edge.uploader.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        result = await upload_file(jpeg_file, settings)
    assert result.outcome == UploadOutcome.REJECTED
    assert result.reason is not None and "too large" in result.reason


@pytest.mark.asyncio
async def test_upload_415_returns_rejected(jpeg_file, settings):
    mock_response = _mock_response(415, {"detail": "unsupported media"})
    with patch("joggy_edge.uploader.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        result = await upload_file(jpeg_file, settings)
    assert result.outcome == UploadOutcome.REJECTED


@pytest.mark.asyncio
async def test_upload_401_returns_auth_failed(jpeg_file, settings):
    mock_response = _mock_response(401, {"detail": "invalid token"})
    with patch("joggy_edge.uploader.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        result = await upload_file(jpeg_file, settings)
    assert result.outcome == UploadOutcome.AUTH_FAILED


@pytest.mark.asyncio
async def test_upload_403_returns_auth_failed(jpeg_file, settings):
    mock_response = _mock_response(403, {"detail": "forbidden"})
    with patch("joggy_edge.uploader.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        result = await upload_file(jpeg_file, settings)
    assert result.outcome == UploadOutcome.AUTH_FAILED


@pytest.mark.asyncio
async def test_upload_includes_bearer_auth_header(jpeg_file, settings):
    """Verify Authorization: Bearer <token> header sent."""
    mock_response = _mock_response(202, {"photo_id": "x", "job_id": "y", "status": "queued"})
    with patch("joggy_edge.uploader.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        await upload_file(jpeg_file, settings)
    call_kwargs = instance.post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer evt_test_token"


@pytest.mark.asyncio
async def test_upload_multipart_includes_device_id(jpeg_file, settings):
    mock_response = _mock_response(202, {"photo_id": "x", "job_id": "y", "status": "queued"})
    with patch("joggy_edge.uploader.httpx.AsyncClient") as MockClient:
        instance = MockClient.return_value.__aenter__.return_value
        instance.post = AsyncMock(return_value=mock_response)
        await upload_file(jpeg_file, settings)
    call_kwargs = instance.post.call_args.kwargs
    # device_id is in data (form fields), file is in files
    assert call_kwargs["data"]["device_id"] == "pi-001"
    assert "captured_at" in call_kwargs["data"]
    assert "file" in call_kwargs["files"]


@pytest.mark.asyncio
async def test_upload_with_retry_succeeds_after_5xx(jpeg_file, settings, tmp_path, monkeypatch):
    """5xx response triggers retry; second attempt succeeds."""
    monkeypatch.setattr(settings, "stuck_marker_path", str(tmp_path / "stuck"))
    from joggy_edge.uploader import upload_with_retry

    call_count = {"n": 0}

    async def fake_upload(path, s):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise httpx.HTTPStatusError(
                "500",
                request=httpx.Request("POST", "https://vps.example/ingest/photos"),
                response=_mock_response(500, {}),
            )
        return UploadResult(outcome=UploadOutcome.UPLOADED, photo_id="x", job_id="y")

    with patch("joggy_edge.uploader.upload_file", side_effect=fake_upload), \
         patch("joggy_edge.uploader._RETRY_WAIT_MULTIPLIER", 0.01):  # speed up test
        result = await upload_with_retry(jpeg_file, settings)
    assert result.outcome == UploadOutcome.UPLOADED
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_upload_with_retry_touches_stuck_marker_after_threshold(jpeg_file, settings, tmp_path, monkeypatch):
    """After N failed attempts, stuck marker file is created."""
    marker = tmp_path / "stuck"
    monkeypatch.setattr(settings, "stuck_marker_path", str(marker))
    monkeypatch.setattr(settings, "stuck_alert_threshold", 2)
    from joggy_edge.uploader import upload_with_retry

    call_count = {"n": 0}

    async def fake_upload(path, s):
        call_count["n"] += 1
        if call_count["n"] < 4:
            raise httpx.ConnectError("network down")
        return UploadResult(outcome=UploadOutcome.UPLOADED, photo_id="x", job_id="y")

    with patch("joggy_edge.uploader.upload_file", side_effect=fake_upload), \
         patch("joggy_edge.uploader._RETRY_WAIT_MULTIPLIER", 0.01):
        result = await upload_with_retry(jpeg_file, settings)
    assert result.outcome == UploadOutcome.UPLOADED
    # Marker should have been touched at some point (and may still exist)
    assert marker.exists()
