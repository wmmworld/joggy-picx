# Edge Uploader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Raspberry Pi 5 edge uploader daemon — watches `/home/pi/photos/inbox/`, uploads new JPEGs to VPS `/ingest/photos` with event token auth, retries on failure, moves to `uploaded/YYYY-MM-DD/` on success.

**Architecture:** inotify-based daemon (decoupled from gphoto2), built with `watchdog` library for filesystem events, `httpx` for async HTTP, `tenacity` for exponential retry, `pydantic-settings` for .env config. systemd service for auto-start. File system serves as persistent queue — no separate DB.

**Tech Stack:** Python 3.11+, asyncio, httpx, watchdog, tenacity, pydantic, pydantic-settings, pytest with `pytest-asyncio`. Deployment: systemd on Raspberry Pi OS 64-bit.

---

## File Map

**Create:**
- `apps/edge/joggy_edge/config.py` — pydantic-settings `EdgeSettings`
- `apps/edge/joggy_edge/uploader.py` — `upload_file()` + `UploadOutcome`/`UploadResult`
- `apps/edge/joggy_edge/watcher.py` — watchdog observer + consumer loop + file moves
- `apps/edge/joggy_edge/__main__.py` — daemon entry point (signal handling)
- `apps/edge/.env.example` — config template
- `apps/edge/infra/joggy-edge.service` — systemd unit
- `apps/edge/tests/__init__.py`
- `apps/edge/tests/test_config.py`
- `apps/edge/tests/test_uploader.py`
- `apps/edge/tests/test_watcher.py`

**Modify:**
- `apps/edge/pyproject.toml` — add `pydantic-settings`, add pytest-asyncio + asyncio_mode config
- `apps/edge/README.md` — replace skeleton with full setup guide

---

## Task 1: Add deps + pytest-asyncio config

**Files:**
- Modify: `apps/edge/pyproject.toml`

- [ ] **Step 1: Read current pyproject.toml**

```bash
cat apps/edge/pyproject.toml
```

- [ ] **Step 2: Add `pydantic-settings` to dependencies and configure pytest**

Edit `apps/edge/pyproject.toml`:

```toml
# Codex: นิยาม package และ dependencies สำหรับ Raspberry Pi edge uploader/watchdog
[project]
name = "joggy-edge"
version = "0.1.0"
description = "Joggy-PicX edge uploader package for Raspberry Pi."
readme = "README.md"
requires-python = ">=3.11,<3.13"
dependencies = [
  "httpx>=0.28.0,<1.0.0",
  "watchdog>=6.0.0,<7.0.0",
  "tenacity>=9.1.0,<10.0.0",
  "pydantic>=2.11.0,<3.0.0",
  "pydantic-settings>=2.10.0,<3.0.0",
]

[dependency-groups]
dev = [
  "ruff>=0.12.0,<1.0.0",
  "mypy>=1.17.0,<2.0.0",
  "pytest>=8.4.0,<9.0.0",
  "pytest-asyncio>=0.23.0,<1.0.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["joggy_edge"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: Sync deps**

```bash
cd apps/edge
uv sync
```

Expected: `pydantic-settings` + `pytest-asyncio` installed.

- [ ] **Step 4: Create tests directory**

```bash
mkdir -p tests
touch tests/__init__.py
```

- [ ] **Step 5: Verify package importable**

```bash
uv run python -c "import joggy_edge; print('ok')"
```

Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add apps/edge/pyproject.toml apps/edge/tests/__init__.py
git commit -m "feat(edge): add pydantic-settings + pytest-asyncio for edge uploader

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: `config.py` — EdgeSettings (TDD)

**Files:**
- Create: `apps/edge/joggy_edge/config.py`
- Create: `apps/edge/tests/test_config.py`
- Create: `apps/edge/.env.example`

- [ ] **Step 1: Write the failing test**

Create `apps/edge/tests/test_config.py`:

```python
"""Tests for EdgeSettings — pydantic-settings config loader."""
import os

import pytest
from pydantic import ValidationError

from joggy_edge.config import EdgeSettings


def test_loads_required_fields_from_env(monkeypatch):
    monkeypatch.setenv("INGEST_URL", "https://vps.example/ingest/photos")
    monkeypatch.setenv("EVENT_TOKEN", "evt_test_abc123")
    # Disable .env file loading by changing to empty cwd
    monkeypatch.chdir(os.path.dirname(__file__))
    s = EdgeSettings(_env_file=None)  # type: ignore[call-arg]
    assert str(s.ingest_url).startswith("https://vps.example/")
    assert s.event_token == "evt_test_abc123"
    # Defaults
    assert s.device_id == "pi-001"
    assert s.inbox_dir == "/home/pi/photos/inbox"
    assert s.uploaded_dir == "/home/pi/photos/uploaded"
    assert s.failed_dir == "/home/pi/photos/failed"
    assert s.log_level == "INFO"
    assert s.request_timeout_seconds == 30.0
    assert s.stuck_alert_threshold == 3
    assert s.stuck_marker_path == "/tmp/joggy-edge-stuck"


def test_overrides_defaults_from_env(monkeypatch):
    monkeypatch.setenv("INGEST_URL", "https://vps.example/ingest/photos")
    monkeypatch.setenv("EVENT_TOKEN", "evt_test")
    monkeypatch.setenv("DEVICE_ID", "pi-007")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = EdgeSettings(_env_file=None)  # type: ignore[call-arg]
    assert s.device_id == "pi-007"
    assert s.log_level == "DEBUG"


def test_missing_event_token_raises(monkeypatch):
    monkeypatch.delenv("EVENT_TOKEN", raising=False)
    monkeypatch.setenv("INGEST_URL", "https://vps.example/ingest/photos")
    with pytest.raises(ValidationError):
        EdgeSettings(_env_file=None)  # type: ignore[call-arg]


def test_invalid_url_raises(monkeypatch):
    monkeypatch.setenv("INGEST_URL", "not-a-url")
    monkeypatch.setenv("EVENT_TOKEN", "evt_test")
    with pytest.raises(ValidationError):
        EdgeSettings(_env_file=None)  # type: ignore[call-arg]
```

- [ ] **Step 2: Run to verify failure**

```bash
cd apps/edge
uv run pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'joggy_edge.config'`

- [ ] **Step 3: Write `config.py`**

Create `apps/edge/joggy_edge/config.py`:

```python
"""Edge uploader configuration — loaded from .env via pydantic-settings."""
from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class EdgeSettings(BaseSettings):
    """Settings for the Pi edge uploader daemon.

    Loaded from /home/pi/joggy/.env (when deployed) or .env in working dir.
    Required fields raise ValidationError if missing.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Required ──────────────────────────────────────────────────────────────
    ingest_url: HttpUrl  # e.g. https://vps.joggy.example/ingest/photos
    event_token: str  # Per-event upload token (D-017)

    # ── Identification ────────────────────────────────────────────────────────
    device_id: str = "pi-001"

    # ── Filesystem layout ─────────────────────────────────────────────────────
    inbox_dir: str = "/home/pi/photos/inbox"
    uploaded_dir: str = "/home/pi/photos/uploaded"
    failed_dir: str = "/home/pi/photos/failed"

    # ── Behavior ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    request_timeout_seconds: float = 30.0

    # ── Alerting ──────────────────────────────────────────────────────────────
    stuck_alert_threshold: int = 3  # touch marker after N consecutive retries
    stuck_marker_path: str = "/tmp/joggy-edge-stuck"
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Create `.env.example`**

Create `apps/edge/.env.example`:

```
# Joggy-PicX Edge Uploader configuration
# Copy this file to /home/pi/joggy/.env on the Pi and fill in real values

# Required — Backend ingest endpoint URL
INGEST_URL=https://vps.example.com/ingest/photos

# Required — Per-Event Upload Token (get from admin dashboard for the active event)
EVENT_TOKEN=evt_REPLACE_ME

# Optional — identifies this Pi in audit logs
DEVICE_ID=pi-001

# Optional — filesystem layout (defaults shown)
# INBOX_DIR=/home/pi/photos/inbox
# UPLOADED_DIR=/home/pi/photos/uploaded
# FAILED_DIR=/home/pi/photos/failed

# Optional — behavior
# LOG_LEVEL=INFO
# REQUEST_TIMEOUT_SECONDS=30.0
# STUCK_ALERT_THRESHOLD=3
# STUCK_MARKER_PATH=/tmp/joggy-edge-stuck
```

- [ ] **Step 6: Commit**

```bash
git add apps/edge/joggy_edge/config.py apps/edge/tests/test_config.py apps/edge/.env.example
git commit -m "feat(edge): EdgeSettings config + .env.example

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: `uploader.py` — Upload outcome types + happy path test

**Files:**
- Create: `apps/edge/joggy_edge/uploader.py`
- Create: `apps/edge/tests/test_uploader.py`

- [ ] **Step 1: Write the failing test**

Create `apps/edge/tests/test_uploader.py`:

```python
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
```

- [ ] **Step 2: Run to verify failure**

```bash
uv run pytest tests/test_uploader.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'joggy_edge.uploader'`

- [ ] **Step 3: Write `uploader.py`**

Create `apps/edge/joggy_edge/uploader.py`:

```python
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
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_uploader.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add apps/edge/joggy_edge/uploader.py apps/edge/tests/test_uploader.py
git commit -m "feat(edge): upload_file() + UploadOutcome enum + response handling

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Retry wrapper + stuck marker

**Files:**
- Modify: `apps/edge/joggy_edge/uploader.py`
- Modify: `apps/edge/tests/test_uploader.py`

- [ ] **Step 1: Add retry test**

Append to `apps/edge/tests/test_uploader.py`:

```python
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
```

- [ ] **Step 2: Run tests — expect failure**

```bash
uv run pytest tests/test_uploader.py::test_upload_with_retry_succeeds_after_5xx -v
```

Expected: FAIL — `cannot import name 'upload_with_retry'`

- [ ] **Step 3: Add retry wrapper to uploader.py**

Append to `apps/edge/joggy_edge/uploader.py`:

```python
from pathlib import Path as _Path

from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_never,
    wait_exponential,
)

# Tunable multiplier (patched in tests for speed)
_RETRY_WAIT_MULTIPLIER: float = 5.0


async def upload_with_retry(path: Path, settings: EdgeSettings) -> UploadResult:
    """Wrap upload_file with exponential retry on httpx errors.

    Retries on httpx.HTTPError and TimeoutException; never stops (file stays
    in inbox until success). After `stuck_alert_threshold` attempts, touches
    the stuck marker file to alert ops.
    """
    attempt_no = 0

    async for attempt in AsyncRetrying(
        retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
        wait=wait_exponential(multiplier=_RETRY_WAIT_MULTIPLIER, min=_RETRY_WAIT_MULTIPLIER, max=300),
        stop=stop_never,
        reraise=True,
    ):
        with attempt:
            attempt_no += 1
            if attempt_no == settings.stuck_alert_threshold:
                try:
                    _Path(settings.stuck_marker_path).touch()
                    logger.warning(
                        "STUCK: upload of %s failed %d times — touched %s",
                        path.name,
                        attempt_no - 1,
                        settings.stuck_marker_path,
                    )
                except OSError as e:
                    logger.error("Cannot touch stuck marker: %s", e)
            return await upload_file(path, settings)

    # Unreachable (stop_never), but satisfy type checker
    raise RuntimeError("upload_with_retry exited unexpectedly")
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_uploader.py -v
```

Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add apps/edge/joggy_edge/uploader.py apps/edge/tests/test_uploader.py
git commit -m "feat(edge): upload_with_retry — exponential backoff + stuck marker alert

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: `watcher.py` — File move helpers

**Files:**
- Create: `apps/edge/joggy_edge/watcher.py`
- Create: `apps/edge/tests/test_watcher.py`

- [ ] **Step 1: Write the failing test**

Create `apps/edge/tests/test_watcher.py`:

```python
"""Tests for watcher — file move helpers + extension filter + scan."""
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    inbox = tmp_path / "inbox"
    uploaded = tmp_path / "uploaded"
    failed = tmp_path / "failed"
    for d in (inbox, uploaded, failed):
        d.mkdir()
    return inbox, uploaded, failed


def test_move_to_uploaded_creates_date_folder(tmp_path):
    from joggy_edge.watcher import move_to_uploaded

    inbox, uploaded, _ = _make_dirs(tmp_path)
    f = inbox / "photo.jpg"
    f.write_bytes(b"x")

    fixed_date = datetime(2026, 6, 1)
    with patch("joggy_edge.watcher._today", return_value=fixed_date):
        result = move_to_uploaded(f, uploaded)

    assert not f.exists()
    expected = uploaded / "2026-06-01" / "photo.jpg"
    assert expected.exists()
    assert result == expected


def test_move_to_uploaded_suffix_on_collision(tmp_path):
    from joggy_edge.watcher import move_to_uploaded

    inbox, uploaded, _ = _make_dirs(tmp_path)
    fixed_date = datetime(2026, 6, 1)
    date_folder = uploaded / "2026-06-01"
    date_folder.mkdir()
    existing = date_folder / "photo.jpg"
    existing.write_bytes(b"old")

    new_file = inbox / "photo.jpg"
    new_file.write_bytes(b"new")

    with patch("joggy_edge.watcher._today", return_value=fixed_date):
        result = move_to_uploaded(new_file, uploaded)

    assert existing.read_bytes() == b"old"
    assert result == date_folder / "photo_2.jpg"
    assert result.read_bytes() == b"new"


def test_move_to_failed(tmp_path):
    from joggy_edge.watcher import move_to_failed

    inbox, _, failed = _make_dirs(tmp_path)
    f = inbox / "bad.jpg"
    f.write_bytes(b"x")

    result = move_to_failed(f, failed)

    assert not f.exists()
    assert result == failed / "bad.jpg"
    assert result.exists()


def test_is_image_file_accepts_jpeg_and_png():
    from joggy_edge.watcher import is_image_file

    assert is_image_file(Path("a.jpg"))
    assert is_image_file(Path("a.jpeg"))
    assert is_image_file(Path("a.JPG"))
    assert is_image_file(Path("a.png"))
    assert is_image_file(Path("a.PNG"))


def test_is_image_file_rejects_other():
    from joggy_edge.watcher import is_image_file

    assert not is_image_file(Path("a.txt"))
    assert not is_image_file(Path("a.tmp"))
    assert not is_image_file(Path("a"))
    assert not is_image_file(Path(".hidden.jpg"))


def test_scan_inbox_returns_image_files_only(tmp_path):
    from joggy_edge.watcher import scan_inbox

    inbox, _, _ = _make_dirs(tmp_path)
    (inbox / "a.jpg").write_bytes(b"")
    (inbox / "b.png").write_bytes(b"")
    (inbox / "c.txt").write_bytes(b"")
    (inbox / "d.tmp").write_bytes(b"")
    (inbox / ".hidden.jpg").write_bytes(b"")

    results = sorted(p.name for p in scan_inbox(inbox))
    assert results == ["a.jpg", "b.png"]


def test_wait_for_stable_size_returns_true_when_stable(tmp_path):
    from joggy_edge.watcher import wait_for_stable_size

    f = tmp_path / "x.jpg"
    f.write_bytes(b"hello")
    assert wait_for_stable_size(f, poll_interval=0.01, max_wait=0.1) is True


def test_wait_for_stable_size_returns_false_when_growing(tmp_path, monkeypatch):
    """File whose size keeps changing returns False after max_wait."""
    from joggy_edge.watcher import wait_for_stable_size

    f = tmp_path / "x.jpg"
    f.write_bytes(b"a")
    sizes = iter([1, 2, 3, 4, 5, 6])
    monkeypatch.setattr(
        "joggy_edge.watcher._file_size",
        lambda p: next(sizes, 99),
    )
    assert wait_for_stable_size(f, poll_interval=0.01, max_wait=0.05) is False
```

- [ ] **Step 2: Run tests — expect failure**

```bash
uv run pytest tests/test_watcher.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'joggy_edge.watcher'`

- [ ] **Step 3: Create `watcher.py` with move + filter helpers**

Create `apps/edge/joggy_edge/watcher.py`:

```python
"""Filesystem observer + consumer loop for the edge uploader."""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _today() -> datetime:
    """Wrappable for tests."""
    return datetime.now()


def _file_size(path: Path) -> int:
    """Wrappable for tests."""
    return path.stat().st_size


def is_image_file(path: Path) -> bool:
    """True if path is a JPEG/PNG and not a hidden file."""
    if path.name.startswith("."):
        return False
    return path.suffix.lower() in _IMAGE_EXTENSIONS


def scan_inbox(inbox: Path) -> list[Path]:
    """List image files in inbox (non-recursive). Sorted for deterministic order."""
    if not inbox.exists():
        return []
    return sorted(p for p in inbox.iterdir() if p.is_file() and is_image_file(p))


def wait_for_stable_size(path: Path, poll_interval: float = 0.1, max_wait: float = 2.0) -> bool:
    """Poll file size until it stops changing.

    Returns True if size is stable (2 consecutive reads equal). Returns False
    if max_wait elapsed without stabilizing — caller should skip or retry later.
    """
    deadline = time.monotonic() + max_wait
    try:
        prev = _file_size(path)
    except FileNotFoundError:
        return False
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        try:
            curr = _file_size(path)
        except FileNotFoundError:
            return False
        if curr == prev and curr > 0:
            return True
        prev = curr
    return False


def move_to_uploaded(file_path: Path, uploaded_root: Path) -> Path:
    """Move file to uploaded/YYYY-MM-DD/. Suffix `_2`, `_3`... on collision."""
    date_folder = uploaded_root / _today().strftime("%Y-%m-%d")
    date_folder.mkdir(parents=True, exist_ok=True)
    target = _resolve_collision(date_folder / file_path.name)
    file_path.rename(target)
    return target


def move_to_failed(file_path: Path, failed_root: Path) -> Path:
    """Move file to failed/ with collision suffix."""
    failed_root.mkdir(parents=True, exist_ok=True)
    target = _resolve_collision(failed_root / file_path.name)
    file_path.rename(target)
    return target


def _resolve_collision(target: Path) -> Path:
    """Return target if not exists; else append `_2`, `_3`... before extension."""
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    n = 2
    while True:
        candidate = target.with_name(f"{stem}_{n}{suffix}")
        if not candidate.exists():
            return candidate
        n += 1
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_watcher.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add apps/edge/joggy_edge/watcher.py apps/edge/tests/test_watcher.py
git commit -m "feat(edge): watcher helpers — move + filter + scan + stability check

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: `watcher.py` — Consumer loop + observer wiring

**Files:**
- Modify: `apps/edge/joggy_edge/watcher.py`
- Modify: `apps/edge/tests/test_watcher.py`

- [ ] **Step 1: Add consumer + observer tests**

Append to `apps/edge/tests/test_watcher.py`:

```python
import asyncio
from unittest.mock import AsyncMock

from joggy_edge.config import EdgeSettings
from joggy_edge.uploader import UploadOutcome, UploadResult


@pytest.fixture
def settings_for_watch(tmp_path, monkeypatch):
    monkeypatch.setenv("INGEST_URL", "https://vps.example/ingest/photos")
    monkeypatch.setenv("EVENT_TOKEN", "evt")
    monkeypatch.setenv("INBOX_DIR", str(tmp_path / "inbox"))
    monkeypatch.setenv("UPLOADED_DIR", str(tmp_path / "uploaded"))
    monkeypatch.setenv("FAILED_DIR", str(tmp_path / "failed"))
    s = EdgeSettings(_env_file=None)  # type: ignore[call-arg]
    for d in (s.inbox_dir, s.uploaded_dir, s.failed_dir):
        Path(d).mkdir(parents=True, exist_ok=True)
    return s


@pytest.mark.asyncio
async def test_consumer_uploaded_moves_to_uploaded_folder(settings_for_watch, monkeypatch):
    from joggy_edge import watcher

    f = Path(settings_for_watch.inbox_dir) / "good.jpg"
    f.write_bytes(b"x")

    monkeypatch.setattr(
        watcher,
        "upload_with_retry",
        AsyncMock(return_value=UploadResult(outcome=UploadOutcome.UPLOADED, photo_id="p", job_id="j")),
    )
    monkeypatch.setattr(
        watcher, "wait_for_stable_size", lambda p, **kw: True
    )

    queue: asyncio.Queue[Path] = asyncio.Queue()
    await queue.put(f)

    task = asyncio.create_task(watcher.consumer_loop(queue, settings_for_watch, stop_after=1))
    await task

    assert not f.exists()
    assert any(Path(settings_for_watch.uploaded_dir).rglob("good.jpg"))


@pytest.mark.asyncio
async def test_consumer_rejected_moves_to_failed_folder(settings_for_watch, monkeypatch):
    from joggy_edge import watcher

    f = Path(settings_for_watch.inbox_dir) / "bad.jpg"
    f.write_bytes(b"x")

    monkeypatch.setattr(
        watcher,
        "upload_with_retry",
        AsyncMock(return_value=UploadResult(outcome=UploadOutcome.REJECTED, reason="too large")),
    )
    monkeypatch.setattr(watcher, "wait_for_stable_size", lambda p, **kw: True)

    queue: asyncio.Queue[Path] = asyncio.Queue()
    await queue.put(f)
    await watcher.consumer_loop(queue, settings_for_watch, stop_after=1)

    assert not f.exists()
    assert (Path(settings_for_watch.failed_dir) / "bad.jpg").exists()


@pytest.mark.asyncio
async def test_consumer_auth_failed_raises_authrequired(settings_for_watch, monkeypatch):
    from joggy_edge import watcher
    from joggy_edge.watcher import AuthRequired

    f = Path(settings_for_watch.inbox_dir) / "x.jpg"
    f.write_bytes(b"x")

    monkeypatch.setattr(
        watcher,
        "upload_with_retry",
        AsyncMock(return_value=UploadResult(outcome=UploadOutcome.AUTH_FAILED, reason="invalid")),
    )
    monkeypatch.setattr(watcher, "wait_for_stable_size", lambda p, **kw: True)

    queue: asyncio.Queue[Path] = asyncio.Queue()
    await queue.put(f)

    with pytest.raises(AuthRequired):
        await watcher.consumer_loop(queue, settings_for_watch, stop_after=1)


@pytest.mark.asyncio
async def test_consumer_skips_when_size_unstable(settings_for_watch, monkeypatch):
    from joggy_edge import watcher

    f = Path(settings_for_watch.inbox_dir) / "growing.jpg"
    f.write_bytes(b"x")

    upload_mock = AsyncMock()
    monkeypatch.setattr(watcher, "upload_with_retry", upload_mock)
    monkeypatch.setattr(watcher, "wait_for_stable_size", lambda p, **kw: False)

    queue: asyncio.Queue[Path] = asyncio.Queue()
    await queue.put(f)
    await watcher.consumer_loop(queue, settings_for_watch, stop_after=1)

    upload_mock.assert_not_called()
    assert f.exists()  # left in inbox
```

- [ ] **Step 2: Run tests — expect failure**

```bash
uv run pytest tests/test_watcher.py -v
```

Expected: failures about missing `consumer_loop` / `AuthRequired` / `upload_with_retry`.

- [ ] **Step 3: Add consumer loop + AuthRequired to watcher.py**

Append to `apps/edge/joggy_edge/watcher.py`:

```python
import asyncio

from joggy_edge.config import EdgeSettings
from joggy_edge.uploader import UploadOutcome, UploadResult, upload_with_retry  # noqa: F401 — re-exported for tests


class AuthRequired(Exception):
    """Raised when the daemon receives 401/403 — token must be fixed before continuing."""


async def consumer_loop(
    queue: "asyncio.Queue[Path]",
    settings: EdgeSettings,
    stop_after: int | None = None,
) -> None:
    """Drain queue, upload each file, dispatch to uploaded/ or failed/.

    Raises AuthRequired on AUTH_FAILED (caller stops the daemon).
    `stop_after`: if set, exits after processing N items (used in tests).
    """
    inbox = Path(settings.inbox_dir)  # noqa: F841 — accessed via settings later if needed
    uploaded_root = Path(settings.uploaded_dir)
    failed_root = Path(settings.failed_dir)
    processed = 0

    while stop_after is None or processed < stop_after:
        try:
            path = await asyncio.wait_for(queue.get(), timeout=1.0) if stop_after else await queue.get()
        except asyncio.TimeoutError:
            return

        try:
            if not path.exists():
                logger.warning("File disappeared before upload: %s", path)
                continue
            if not wait_for_stable_size(path):
                logger.warning("File size unstable, skipping (will retry on restart): %s", path)
                continue

            result: UploadResult = await upload_with_retry(path, settings)
            if result.outcome in (UploadOutcome.UPLOADED, UploadOutcome.DUPLICATE):
                target = move_to_uploaded(path, uploaded_root)
                logger.info(
                    "Uploaded %s → %s (photo_id=%s, outcome=%s)",
                    path.name, target.name, result.photo_id, result.outcome.value,
                )
            elif result.outcome == UploadOutcome.REJECTED:
                target = move_to_failed(path, failed_root)
                logger.error("Rejected %s → %s (reason=%s)", path.name, target.name, result.reason)
            elif result.outcome == UploadOutcome.AUTH_FAILED:
                logger.critical("AUTH_FAILED on %s (reason=%s) — stopping daemon", path.name, result.reason)
                raise AuthRequired(result.reason or "token rejected")
        finally:
            queue.task_done()
            processed += 1
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_watcher.py -v
```

Expected: `12 passed`

- [ ] **Step 5: Commit**

```bash
git add apps/edge/joggy_edge/watcher.py apps/edge/tests/test_watcher.py
git commit -m "feat(edge): consumer_loop — dispatch uploads + file lifecycle

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Observer + startup scan dispatch

**Files:**
- Modify: `apps/edge/joggy_edge/watcher.py`
- Modify: `apps/edge/tests/test_watcher.py`

- [ ] **Step 1: Add observer + startup_scan tests**

Append to `apps/edge/tests/test_watcher.py`:

```python
@pytest.mark.asyncio
async def test_startup_scan_enqueues_existing_files(settings_for_watch):
    from joggy_edge.watcher import startup_scan

    inbox = Path(settings_for_watch.inbox_dir)
    (inbox / "a.jpg").write_bytes(b"")
    (inbox / "b.png").write_bytes(b"")
    (inbox / "c.txt").write_bytes(b"")  # should be skipped

    queue: asyncio.Queue[Path] = asyncio.Queue()
    await startup_scan(inbox, queue)

    enqueued = []
    while not queue.empty():
        enqueued.append(queue.get_nowait().name)
    assert sorted(enqueued) == ["a.jpg", "b.png"]


def test_make_handler_enqueues_image_create(settings_for_watch, tmp_path):
    """FileCreatedEvent for image triggers queue.put_nowait."""
    from joggy_edge.watcher import _Handler

    loop_calls: list[Path] = []
    class FakeLoop:
        def call_soon_threadsafe(self, fn, *args):
            fn(*args)
    queue_calls: list[Path] = []
    class FakeQueue:
        def put_nowait(self, item):
            queue_calls.append(item)

    handler = _Handler(loop=FakeLoop(), queue=FakeQueue())  # type: ignore[arg-type]

    class FakeEvent:
        def __init__(self, src_path: str, is_directory: bool = False):
            self.src_path = src_path
            self.is_directory = is_directory

    handler.on_created(FakeEvent(str(tmp_path / "img.jpg")))
    handler.on_created(FakeEvent(str(tmp_path / "notes.txt")))  # not image
    handler.on_created(FakeEvent(str(tmp_path), is_directory=True))  # directory

    assert queue_calls == [Path(tmp_path / "img.jpg")]
```

- [ ] **Step 2: Run — expect failure**

```bash
uv run pytest tests/test_watcher.py -v -k "startup_scan or make_handler"
```

Expected: FAIL — missing names.

- [ ] **Step 3: Implement startup_scan + observer wiring**

Append to `apps/edge/joggy_edge/watcher.py`:

```python
from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer


async def startup_scan(inbox: Path, queue: "asyncio.Queue[Path]") -> None:
    """Enqueue all existing image files in inbox (called once at daemon start)."""
    for path in scan_inbox(inbox):
        await queue.put(path)
        logger.info("Startup scan enqueued: %s", path.name)


class _Handler(FileSystemEventHandler):
    """Translates watchdog FileCreatedEvent → queue.put_nowait via event loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: "asyncio.Queue[Path]") -> None:
        super().__init__()
        self._loop = loop
        self._queue = queue

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if getattr(event, "is_directory", False):
            return
        path = Path(str(event.src_path))
        if not is_image_file(path):
            return
        self._loop.call_soon_threadsafe(self._queue.put_nowait, path)


def start_observer(inbox: Path, queue: "asyncio.Queue[Path]", loop: asyncio.AbstractEventLoop) -> Observer:
    """Start watchdog Observer; caller is responsible for stop() on shutdown."""
    inbox.mkdir(parents=True, exist_ok=True)
    handler = _Handler(loop=loop, queue=queue)
    observer = Observer()
    observer.schedule(handler, str(inbox), recursive=False)
    observer.start()
    logger.info("Observer started on %s", inbox)
    return observer
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/test_watcher.py -v
```

Expected: `14 passed`

- [ ] **Step 5: Commit**

```bash
git add apps/edge/joggy_edge/watcher.py apps/edge/tests/test_watcher.py
git commit -m "feat(edge): startup_scan + watchdog observer for FileCreatedEvent

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: `__main__.py` — Daemon entrypoint

**Files:**
- Create: `apps/edge/joggy_edge/__main__.py`

- [ ] **Step 1: Create `__main__.py`**

Create `apps/edge/joggy_edge/__main__.py`:

```python
"""Daemon entry point — `python -m joggy_edge`.

Loads EdgeSettings, starts watcher + observer, handles SIGTERM/SIGINT
gracefully. Exits non-zero if AUTH_FAILED — systemd will retry, but ops
must fix the token first.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from joggy_edge.config import EdgeSettings
from joggy_edge.watcher import (
    AuthRequired,
    consumer_loop,
    start_observer,
    startup_scan,
)

logger = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def _run() -> int:
    settings = EdgeSettings()  # type: ignore[call-arg]
    _setup_logging(settings.log_level)
    logger.info("joggy-edge starting — inbox=%s ingest=%s", settings.inbox_dir, settings.ingest_url)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Path] = asyncio.Queue()

    inbox = Path(settings.inbox_dir)
    observer = start_observer(inbox, queue, loop)

    # Run startup scan first (drain anything left from previous session)
    await startup_scan(inbox, queue)

    stop_event = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler — fine for tests
            pass

    consumer_task = asyncio.create_task(consumer_loop(queue, settings))

    # Wait for either: stop signal, or consumer exits (auth failure etc.)
    stop_wait = asyncio.create_task(stop_event.wait())
    done, _pending = await asyncio.wait(
        {consumer_task, stop_wait},
        return_when=asyncio.FIRST_COMPLETED,
    )

    exit_code = 0
    try:
        if consumer_task in done:
            consumer_task.result()  # re-raise any exception
    except AuthRequired as e:
        logger.critical("Daemon stopping due to AuthRequired: %s", e)
        exit_code = 1
    except Exception:
        logger.exception("Consumer loop crashed")
        exit_code = 2

    # Shutdown sequence
    logger.info("Stopping observer + consumer …")
    observer.stop()
    observer.join(timeout=2.0)
    if not consumer_task.done():
        consumer_task.cancel()
        try:
            await consumer_task
        except (asyncio.CancelledError, Exception):
            pass

    logger.info("joggy-edge exited with code %d", exit_code)
    return exit_code


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke import check**

```bash
cd apps/edge
uv run python -c "from joggy_edge.__main__ import main; print('ok')"
```

Expected: `ok`

- [ ] **Step 3: Run full test suite — no regressions**

```bash
uv run pytest tests/ -v
```

Expected: `14 passed` (all from previous tasks)

- [ ] **Step 4: Commit**

```bash
git add apps/edge/joggy_edge/__main__.py
git commit -m "feat(edge): daemon __main__ — signal handling + graceful shutdown

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 9: systemd service file

**Files:**
- Create: `apps/edge/infra/joggy-edge.service`

- [ ] **Step 1: Create infra directory + service file**

```bash
mkdir -p apps/edge/infra
```

Create `apps/edge/infra/joggy-edge.service`:

```ini
[Unit]
Description=Joggy-PicX Edge Uploader
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/joggy/apps/edge
EnvironmentFile=/home/pi/joggy/.env
ExecStart=/home/pi/joggy/.venv/bin/python -m joggy_edge
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

- [ ] **Step 2: Commit**

```bash
git add apps/edge/infra/joggy-edge.service
git commit -m "feat(edge): systemd service unit for joggy-edge daemon

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 10: README — deployment + smoke test guide

**Files:**
- Modify: `apps/edge/README.md`

- [ ] **Step 1: Replace skeleton README**

Replace `apps/edge/README.md` with:

````markdown
# Joggy-PicX Edge Uploader (Pi 5)

Inotify-based daemon that watches `/home/pi/photos/inbox/`, uploads JPEGs to the VPS `/ingest/photos` endpoint using a Per-Event Upload Token, and moves uploaded files to `/home/pi/photos/uploaded/YYYY-MM-DD/`.

Design spec: [`docs/superpowers/specs/2026-06-01-edge-uploader-design.md`](../../docs/superpowers/specs/2026-06-01-edge-uploader-design.md)

---

## Deployment on Raspberry Pi 5

### 1. Prerequisites

- Raspberry Pi OS 64-bit (Bookworm)
- `gphoto2`, `uv`, `git` installed (see `docs/canon-tether-test.md`)
- Active event + token from admin dashboard (`/dashboard/events/{id}` → generate token)

### 2. Clone + install

```bash
git clone https://github.com/wmmworld/Joggy-PicX /home/pi/joggy
cd /home/pi/joggy/apps/edge
uv sync
```

### 3. Configure

```bash
cp .env.example /home/pi/joggy/.env
nano /home/pi/joggy/.env
```

Set at minimum:
```
INGEST_URL=https://your-vps.example/ingest/photos
EVENT_TOKEN=evt_REPLACE_ME
DEVICE_ID=pi-001
```

### 4. Create runtime folders

```bash
mkdir -p /home/pi/photos/{inbox,uploaded,failed}
```

### 5. Install systemd service

```bash
sudo cp infra/joggy-edge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now joggy-edge
```

### 6. Verify

```bash
systemctl status joggy-edge
journalctl -u joggy-edge -f
```

You should see `Observer started on /home/pi/photos/inbox`.

### 7. Start gphoto2 capture (separate terminal, manual for MVP)

```bash
gphoto2 --capture-tethered \
  --filename "/home/pi/photos/inbox/%Y%m%d_%H%M%S.jpg"
```

Take a photo — within ~2s the daemon should log `Uploaded ... → /home/pi/photos/uploaded/...`.

---

## Operations

| Task | Command |
|------|---------|
| Tail logs | `journalctl -u joggy-edge -f` |
| Restart after token rotation | `sudo systemctl restart joggy-edge` |
| Stop | `sudo systemctl stop joggy-edge` |
| Check stuck marker | `ls -la /tmp/joggy-edge-stuck*` |
| Cleanup old uploaded (weekly cron) | `find /home/pi/photos/uploaded -mtime +30 -type d -empty -delete` |

---

## Local smoke test (dev laptop)

```bash
cd apps/edge

# Override paths to use a temp dir
mkdir -p /tmp/edge_test/{inbox,uploaded,failed}
cat > .env <<EOF
INGEST_URL=http://localhost:8000/ingest/photos
EVENT_TOKEN=evt_test_token  # get from running backend + dashboard
DEVICE_ID=dev-laptop
INBOX_DIR=/tmp/edge_test/inbox
UPLOADED_DIR=/tmp/edge_test/uploaded
FAILED_DIR=/tmp/edge_test/failed
LOG_LEVEL=DEBUG
EOF

# Terminal 1: start backend (in apps/backend)
# Terminal 2: start daemon
uv run python -m joggy_edge

# Terminal 3: drop a test JPEG
cp some_test.jpg /tmp/edge_test/inbox/

# Watch Terminal 2 — should see Uploaded log
ls /tmp/edge_test/uploaded/
```

---

## Testing

```bash
cd apps/edge
uv run pytest tests/ -v
```

Expected: `14 passed`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Daemon stopping due to AuthRequired` | EVENT_TOKEN invalid or expired | Generate new token from dashboard → update `.env` → restart |
| Files pile up in inbox | Network/VPS issue (check stuck marker) | Check `journalctl -u joggy-edge` for retry logs; verify INGEST_URL reachable |
| `Observer started` but no uploads | gphoto2 writing to wrong folder | Verify `--filename` path matches `INBOX_DIR` |
| Permission denied on photos folder | systemd user (`pi`) lacks access | `chown -R pi:pi /home/pi/photos` |
````

- [ ] **Step 2: Commit**

```bash
git add apps/edge/README.md
git commit -m "docs(edge): deployment + smoke test guide

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 11: Update PROGRESS.md + CHANGELOG.md

**Files:**
- Modify: `PROGRESS.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: PROGRESS — mark edge uploader complete**

In `PROGRESS.md`:
- Update `วันที่อัปเดตล่าสุด` to current date and Claude as updater
- Under Phase 4 milestones, add: `- [x] **Edge uploader (Pi → VPS)** ✅ — inotify daemon, exponential retry, systemd service, 14 TDD tests`

- [ ] **Step 2: CHANGELOG — Added section**

Add to `CHANGELOG.md` under `[Unreleased] > Added`:

```
- [Claude] Edge uploader (Pi 5): `apps/edge/joggy_edge/` package with:
  - `config.py` — EdgeSettings via pydantic-settings (.env loader)
  - `uploader.py` — async upload_file() + UploadOutcome enum (UPLOADED/DUPLICATE/REJECTED/AUTH_FAILED); upload_with_retry() with tenacity exponential backoff (5s→300s capped, no stop) + stuck marker after N attempts
  - `watcher.py` — watchdog observer + asyncio.Queue consumer loop + file move helpers (uploaded/YYYY-MM-DD/, failed/) + extension filter + size-stability check + startup scan
  - `__main__.py` — daemon entry with signal handling + graceful shutdown
  - `infra/joggy-edge.service` — systemd unit
  - 14 TDD tests across config/uploader/watcher
```

- [ ] **Step 3: Commit**

```bash
git add PROGRESS.md CHANGELOG.md
git commit -m "docs: update PROGRESS + CHANGELOG for edge uploader

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Done

After Task 11, the edge uploader is complete:
- 14 passing tests
- 4 Python modules in `joggy_edge/` package
- systemd service ready for Pi deployment
- README + smoke test instructions
- Real photos can flow Canon → Pi → VPS → R2 → Dashboard end-to-end (manual gphoto2 startup; auto-start in Phase 5)
