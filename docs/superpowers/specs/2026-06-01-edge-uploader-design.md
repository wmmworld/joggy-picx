# Edge Uploader (Pi → VPS) Design

**Date:** 2026-06-01
**Author:** Claude (Tech Lead)
**Status:** Approved

---

## Goal

Build the Raspberry Pi 5 edge uploader daemon — watches a local inbox folder, uploads new JPEG photos to the VPS `/ingest/photos` endpoint with Per-Event Upload Token auth (D-017), and handles retries + file lifecycle.

This is the missing piece between validated hardware (Canon EOS RP + gphoto2 USB tether) and the validated backend (POST /ingest/photos). After this lands, real photos flow end-to-end from camera to dashboard.

---

## Scope Decisions

- **Trigger:** inotify-based daemon watching `/home/pi/photos/inbox/` (decoupled from gphoto2)
- **Auth:** Per-Event Upload Token via `Authorization: Bearer` header
- **Retry:** exponential backoff (5s→300s capped), persistent until success
- **Alerting:** after 3 failed attempts → touch marker file + log WARNING
- **File lifecycle:** move to `uploaded/YYYY-MM-DD/` on success (local backup)
- **Config:** `.env` file loaded via pydantic-settings
- **Deploy:** systemd service (auto-start, restart on failure)
- **Out of scope:** auto-start gphoto2 (manual for MVP), Pi → camera trigger (Phase 5)

---

## Architecture

```
gphoto2 (already validated, separate process)
    │
    ▼  writes JPEG
/home/pi/photos/inbox/*.jpg
    │
    ▼  watchdog FileCreatedEvent + startup scan
joggy_edge daemon (systemd service)
    │
    ├─ 1. Wait for file to stabilize (~200ms, size unchanged)
    ├─ 2. Read bytes, multipart POST /ingest/photos
    │      Authorization: Bearer ${EVENT_TOKEN}
    │      file=<bytes>, device_id=${DEVICE_ID}, captured_at=<mtime ISO>
    ├─ 3. Handle response:
    │      202 / 409 → move to uploaded/YYYY-MM-DD/
    │      413 / 415 / 422 → move to failed/ (skip retry — permanent)
    │      401 / 403 → log CRITICAL + stop daemon (token broken)
    │      5xx / network → tenacity retry (exponential, no stop)
    └─ 4. After 3 retry failures → touch /tmp/joggy-edge-stuck + WARNING
```

---

## Components

### File Layout

```
apps/edge/
├── joggy_edge/
│   ├── __init__.py
│   ├── __main__.py           # entry point — load config, start watcher, handle SIGTERM
│   ├── config.py             # pydantic-settings .env loader
│   ├── uploader.py           # upload_file(path) — HTTP POST + retry + response handling
│   └── watcher.py            # watchdog Observer + startup scan + dispatch queue
├── infra/
│   └── joggy-edge.service    # systemd unit file
├── tests/
│   ├── __init__.py
│   ├── test_config.py        # pydantic validation
│   ├── test_uploader.py      # mock httpx, response handling, retry semantics
│   └── test_watcher.py       # mock filesystem, dispatch, startup scan
├── .env.example              # template for /home/pi/joggy/.env
├── pyproject.toml            # already exists with deps: httpx, watchdog, tenacity, pydantic
└── README.md                 # setup guide for Pi deployment
```

### `config.py` — `EdgeSettings`

```python
from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict

class EdgeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ingest_url: HttpUrl                       # e.g. https://vps.joggy.example/ingest/photos
    event_token: str                          # min length validated
    device_id: str = "pi-001"
    inbox_dir: str = "/home/pi/photos/inbox"
    uploaded_dir: str = "/home/pi/photos/uploaded"
    failed_dir: str = "/home/pi/photos/failed"
    log_level: str = "INFO"
    request_timeout_seconds: float = 30.0
    stuck_alert_threshold: int = 3            # touch marker after N retries
    stuck_marker_path: str = "/tmp/joggy-edge-stuck"
```

### `uploader.py` — Single-File Upload

```python
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

class UploadOutcome(str, Enum):
    UPLOADED = "uploaded"       # 202 — move to uploaded/
    DUPLICATE = "duplicate"     # 409 — already in DB, move to uploaded/
    REJECTED = "rejected"       # 413/415/422 — move to failed/, no retry
    AUTH_FAILED = "auth_failed" # 401/403 — daemon should stop
    # 5xx / network → raise → tenacity retries

@dataclass(frozen=True)
class UploadResult:
    outcome: UploadOutcome
    photo_id: str | None = None
    job_id: str | None = None
    reason: str | None = None

async def upload_file(path: Path, settings: EdgeSettings) -> UploadResult: ...
```

Retry via tenacity:
```python
from tenacity import retry, wait_exponential, retry_if_exception_type, stop_never

@retry(
    retry=retry_if_exception_type((httpx.HTTPError, httpx.TimeoutException)),
    wait=wait_exponential(multiplier=5, min=5, max=300),
    stop=stop_never,
    before_sleep=lambda retry_state: _on_retry(retry_state, settings),
)
async def _post_with_retry(client, url, files, headers, timeout) -> httpx.Response: ...
```

`_on_retry` increments attempt counter; when count == `stuck_alert_threshold` → `Path(settings.stuck_marker_path).touch()` + log WARNING.

### `watcher.py` — Inbox Observer

- Uses `watchdog.observers.Observer` + `watchdog.events.FileSystemEventHandler`
- On `on_created` event:
  1. Filter by extension (`.jpg`, `.jpeg`, `.png` — case insensitive)
  2. Wait for file to stabilize: poll `stat().st_size` 2x with 100ms gap; proceed when equal
  3. Push path to `asyncio.Queue` (single-consumer)
- Consumer loop: `await queue.get()` → `await upload_file(path)` → handle outcome:
  - UPLOADED / DUPLICATE → `move_to_uploaded(path)`
  - REJECTED → `move_to_failed(path, reason)`
  - AUTH_FAILED → log CRITICAL + raise to main → daemon exits non-zero (systemd restarts but will re-fail until token fixed)
- Startup: `scan_inbox()` enqueues all existing `.jpg/.png` files

### `__main__.py` — Daemon Entry

```python
import asyncio
import logging
import signal

async def main():
    settings = EdgeSettings()
    setup_logging(settings.log_level)
    queue: asyncio.Queue[Path] = asyncio.Queue()

    observer = start_observer(settings.inbox_dir, queue)
    consumer_task = asyncio.create_task(consumer_loop(queue, settings))
    scan_task = asyncio.create_task(startup_scan(settings.inbox_dir, queue))

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    await stop_event.wait()
    observer.stop()
    consumer_task.cancel()
    # drain in-flight: wait for current upload to finish (or fail) before exit

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Data Flow

```
Pi boot
  └─ systemd starts joggy-edge service
      └─ Settings loaded from /home/pi/joggy/.env
      └─ Logging configured
      └─ Observer attached to inbox_dir
      └─ Startup scan: enqueue any files left from previous session
      └─ Consumer loop awaits queue

gphoto2 captures photo
  └─ Writes /home/pi/photos/inbox/20260601_140532.jpg
      └─ watchdog FileCreatedEvent fires
      └─ Filter extension, wait for stable size (200ms)
      └─ Push path to queue

Consumer picks up
  └─ upload_file(path):
      ├─ Read bytes
      ├─ POST /ingest/photos with event_token
      ├─ Retry on 5xx/network (5s, 10s, 20s, 40s, ...)
      └─ Return UploadResult
  └─ Move file based on outcome
      ├─ 202/409 → uploaded/YYYY-MM-DD/
      ├─ 413/415/422 → failed/
      └─ 401/403 → daemon stops (token problem)

Pi shutdown
  └─ systemd sends SIGTERM
      └─ stop_event set
      └─ Observer stops accepting new events
      └─ Consumer finishes current upload (if any)
      └─ Daemon exits clean
```

---

## Error Handling Matrix

| Scenario | Backend Response | Edge Behavior |
|----------|------------------|---------------|
| Happy path | 202 Accepted | Move to uploaded/, log INFO |
| Duplicate sha256 | 409 Conflict | Move to uploaded/, log DEBUG (no harm) |
| File > 25MB | 413 | Move to failed/, log ERROR |
| Wrong MIME | 415 | Move to failed/, log ERROR |
| Malformed multipart | 422 | Move to failed/, log ERROR |
| Token expired/invalid | 401 / 403 | Log CRITICAL, daemon exits non-zero |
| VPS 5xx | 5xx | Tenacity retry — file stays in inbox |
| Network timeout | TimeoutException | Tenacity retry — file stays in inbox |
| DNS failure | ConnectError | Tenacity retry — file stays in inbox |
| Disk write fail on move | OSError | Log ERROR, leave in inbox, daemon continues |
| File deleted mid-read | FileNotFoundError | Log WARNING, skip, daemon continues |
| Partial write detected | size still changing | Wait, retry stabilize check up to 2s; skip if still unstable |

---

## Testing Approach

### Unit tests (`tests/`)

`test_config.py`:
- Loading from .env with all fields → validates successfully
- Missing `event_token` → ValidationError
- Invalid `ingest_url` (not URL) → ValidationError

`test_uploader.py`:
- 202 response → returns `UploadResult(UPLOADED)` with photo_id parsed from JSON
- 409 response → returns `UploadResult(DUPLICATE)`
- 413/415/422 → returns `UploadResult(REJECTED)` with reason
- 401/403 → returns `UploadResult(AUTH_FAILED)`
- 500 → raises (retry kicks in)
- Network error → raises (retry kicks in)
- Multipart form contains: `file` (binary), `device_id`, `captured_at`
- Authorization header set correctly
- Retry triggered 3 times then `Path(stuck_marker).touch()` called

`test_watcher.py`:
- Pre-populate inbox with 3 JPEGs → startup_scan enqueues 3 paths
- Trigger FileCreatedEvent → consumer receives path
- Non-image files (`.tmp`, `.txt`) ignored
- File stabilization: file mid-write → consumer waits then proceeds
- Move logic: UPLOADED → file appears in `uploaded/2026-06-01/` and gone from inbox
- Filename collision: existing `20260601_140532.jpg` in uploaded/ → new becomes `20260601_140532_2.jpg`

### Manual smoke test (in README)

```bash
# On dev laptop (Windows or Linux):
cd apps/edge
cp .env.example .env
nano .env   # set INGEST_URL=http://localhost:8000/ingest/photos
# Create test event + token via dashboard, paste EVENT_TOKEN
mkdir -p /tmp/edge_test/{inbox,uploaded,failed}
# Override INBOX_DIR etc. in .env to /tmp/edge_test/...
uv run python -m joggy_edge

# In another terminal:
cp some_test.jpg /tmp/edge_test/inbox/
# Watch logs — should see upload + move
ls /tmp/edge_test/uploaded/
```

---

## systemd Deployment

**`infra/joggy-edge.service`:**

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

**Install steps (in README.md):**

```bash
# 1. Clone repo
git clone https://github.com/wmmworld/Joggy-PicX /home/pi/joggy

# 2. Install Python + uv
sudo apt install -y python3-venv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Setup edge package
cd /home/pi/joggy/apps/edge
uv sync

# 4. Configure
cp .env.example /home/pi/joggy/.env
nano /home/pi/joggy/.env
# Paste:
#   INGEST_URL=https://your-vps.example/ingest/photos
#   EVENT_TOKEN=evt_xK9p2_...  (from /dashboard/events/{id} → generate token)
#   DEVICE_ID=pi-001

# 5. Create folders
mkdir -p /home/pi/photos/{inbox,uploaded,failed}

# 6. Install systemd service
sudo cp infra/joggy-edge.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now joggy-edge

# 7. Verify
journalctl -u joggy-edge -f

# 8. Start gphoto2 in separate terminal (manual for MVP)
gphoto2 --capture-tethered \
  --hook-script /home/pi/joggy/on_photo.sh \
  --filename "/home/pi/photos/inbox/%Y%m%d_%H%M%S.jpg"
```

**Operations:**
- View logs: `journalctl -u joggy-edge -f`
- Restart after token rotation: `nano .env` → `sudo systemctl restart joggy-edge`
- Stop: `sudo systemctl stop joggy-edge`
- Cleanup old uploaded: add weekly cron `find /home/pi/photos/uploaded -mtime +30 -delete`

---

## Dependencies

Already in `apps/edge/pyproject.toml`:
- `httpx` — async HTTP client (file upload via multipart)
- `watchdog` — inotify-based filesystem observer
- `tenacity` — retry decorator
- `pydantic` — config validation

To add:
- `pydantic-settings>=2.0` — .env loader (separate from `pydantic` in v2)

---

## Out of Scope (Future Work)

- **Auto-start gphoto2** — currently manual; will be its own systemd service in Phase 5
- **Pi → camera shutter trigger** — Phase 5 mobile / auto-trigger
- **Disk full alerting** — basic mention in stuck_marker, full monitoring later
- **Multi-camera per Pi** — currently 1 inbox = 1 camera; multi-cam in Phase 5
- **OTA config update** — token rotation requires manual `systemctl restart`
- **Metrics push** — log-only for MVP; Prometheus/OpenTelemetry deferred
- **Backfill old files** — manual `mv` to inbox/ + restart works
