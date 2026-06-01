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

Expected: `28 passed`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Daemon stopping due to AuthRequired` | EVENT_TOKEN invalid or expired | Generate new token from dashboard → update `.env` → restart |
| Files pile up in inbox | Network/VPS issue (check stuck marker) | Check `journalctl -u joggy-edge` for retry logs; verify INGEST_URL reachable |
| `Observer started` but no uploads | gphoto2 writing to wrong folder | Verify `--filename` path matches `INBOX_DIR` |
| Permission denied on photos folder | systemd user (`pi`) lacks access | `chown -R pi:pi /home/pi/photos` |
