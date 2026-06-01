"""Upload a single file to the VPS ingest endpoint.

Handles status code mapping to UploadOutcome and exposes a tenacity-wrapped
retry. AUTH_FAILED outcomes signal the daemon to stop (token problem).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

import httpx

from joggy_edge.config import EdgeSettings

logger = logging.getLogger(__name__)


class UploadOutcome(str, Enum):
    """Terminal outcome for a single file upload attempt."""
    UPLOADED = "uploaded"        # 202 — backend accepted; move to uploaded/
    DUPLICATE = "duplicate"      # 409 — backend already has it; move to uploaded/
    REJECTED = "rejected"        # 413/415/422 — permanent failure; move to failed/
    AUTH_FAILED = "auth_failed"  # 401/403 — daemon should stop


@dataclass(frozen=True)
class UploadResult:
    outcome: UploadOutcome
    photo_id: str | None = None
    job_id: str | None = None
    reason: str | None = None


def _captured_at_iso(path: Path) -> str:
    """File mtime as ISO 8601 with UTC tz."""
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return mtime.isoformat()


async def upload_file(path: Path, settings: EdgeSettings) -> UploadResult:
    """Upload one JPEG/PNG to /ingest/photos.

    Raises httpx.HTTPError / TimeoutException on network or 5xx — caller
    should wrap in tenacity retry. Returns UploadResult for terminal outcomes.
    """
    headers = {
        "Authorization": f"Bearer {settings.event_token}",
    }
    data = {
        "device_id": settings.device_id,
        "captured_at": _captured_at_iso(path),
    }
    with path.open("rb") as f:
        file_bytes = f.read()
    files = {"file": (path.name, file_bytes, "image/jpeg")}

    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response: httpx.Response = await client.post(
            str(settings.ingest_url),
            headers=headers,
            data=data,
            files=files,
        )

    status = response.status_code
    body: dict = {}
    try:
        body = response.json()
    except Exception:
        pass

    if status == 202:
        return UploadResult(
            outcome=UploadOutcome.UPLOADED,
            photo_id=body.get("photo_id"),
            job_id=body.get("job_id"),
        )
    if status == 409:
        return UploadResult(outcome=UploadOutcome.DUPLICATE, reason=body.get("detail"))
    if status in (413, 415, 422):
        return UploadResult(outcome=UploadOutcome.REJECTED, reason=body.get("detail") or f"HTTP {status}")
    if status in (401, 403):
        return UploadResult(outcome=UploadOutcome.AUTH_FAILED, reason=body.get("detail") or f"HTTP {status}")

    # 5xx and anything else — raise to trigger retry
    response.raise_for_status()
    # If we reach here, it was an unexpected 2xx/3xx — treat as rejected
    return UploadResult(outcome=UploadOutcome.REJECTED, reason=f"Unexpected status {status}")
