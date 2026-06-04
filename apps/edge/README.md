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

> **Tip for dev mode (laptop as backend):** Use a Tailscale IP instead of LAN IP
> for `INGEST_URL`. Tailscale gives every device a stable 100.x.x.x address that
> doesn't change when WiFi/DHCP renews, so you don't have to re-edit Pi `.env`
> every time the laptop's IP changes. Setup:
> 1. Install Tailscale on both laptop and Pi: https://tailscale.com/download
> 2. Sign in with same account on both: `sudo tailscale up`
> 3. Get laptop's Tailscale IP: `tailscale ip -4` on laptop
> 4. Use that 100.x.x.x address in Pi `.env`: `INGEST_URL=http://100.x.x.x:8000/ingest/photos`
> Tailscale traffic is end-to-end encrypted; no firewall rules needed.

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

### 7. Install gphoto2 capture as user-level service

> **Why user-level?** `gphoto2 --capture-tethered` needs the uaccess ACL that systemd-logind grants only to login sessions of `pi`. A system service (`User=pi`) runs without a session → libgphoto2 fails with `Permission denied` when downloading images from the camera even though group permissions look right. Running as a user service + `loginctl enable-linger pi` keeps the user session alive across reboots so this works headless.

```bash
# A. Belt-and-braces — make Canon USB endpoint plugdev-readable always
sudo cp infra/99-joggy-canon.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules && sudo udevadm trigger --action=change --subsystem-match=usb

# B. Keep pi's user session alive across reboots
sudo loginctl enable-linger pi

# C. Install + enable user service
mkdir -p /home/pi/.config/systemd/user
cp infra/joggy-capture.user.service /home/pi/.config/systemd/user/joggy-capture.service
systemctl --user daemon-reload
systemctl --user enable --now joggy-capture
```

Verify:
```bash
systemctl --user status joggy-capture
journalctl --user -u joggy-capture -f
```

You should see `Waiting for events from camera.` shortly after start.

Take a photo at the camera — within ~2s the edge daemon should log `Uploaded ... → photo_id=...`.

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
| `Permission denied` / `Could not get image` in joggy-capture log | Service installed at system level, not user level → no uaccess ACL → can't read Canon USB endpoint | Reinstall as user service (see step 7). System service `User=pi` does NOT work for gphoto2 tethered. |
| `joggy-capture` not starting at boot | `loginctl enable-linger pi` not set → user session dies on reboot | `sudo loginctl enable-linger pi` |
| Camera shows `ERROR: Could not get image` after manual gphoto2 was killed | Orphan PTP session in camera | Power-cycle the camera; service's `ExecStartPre=gphoto2 --reset` should catch this automatically next time |
