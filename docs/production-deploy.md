# Joggy-PicX Production Deploy Runbook

> **Target:** Hetzner CPX11 (2 vCPU / 2 GB RAM / 40 GB SSD) running Ubuntu 24.04 LTS
> **Author:** Claude (Tech Lead) — Phase 5 production deploy, 2026-06-06
> **Estimated time:** 45–60 นาที สำหรับ first deploy, ~10 นาทีสำหรับ subsequent deploys

แทนที่ `docs/hetzner-setup.md` (Phase 1 skeleton). อ่านครบทุก section ก่อนเริ่ม.

---

## 0. Pre-flight Checklist

CEO ต้องเตรียมไว้ล่วงหน้า:

| Item | Source | Required field |
|------|--------|----------------|
| Hetzner VPS provisioned | hetzner.com → Cloud → Servers | IP address, root SSH access |
| SSH public key | `~/.ssh/id_ed25519.pub` (local) | uploaded ตอน create server |
| Domain name | Cloudflare/Namecheap/etc. | A record → VPS IP |
| Supabase project | supabase.com | URL, anon key, service_role key, JWT secret, DB password |
| Cloudflare R2 bucket | dash.cloudflare.com → R2 | Account ID, Access Key, Secret, bucket name |
| GitHub repo access | github.com | Personal Access Token if private |

> **เคล็ดลับ:** ตอน create Hetzner VM ติ๊ก "Add SSH key" ก่อน — ไม่งั้นต้อง reset password ใน console
> ก่อนเริ่ม

DNS ต้อง resolve **ก่อน** ลงมือ certbot — ทดสอบ: `dig +short YOUR_DOMAIN`

---

## 1. VPS Bootstrap

จาก laptop:

```bash
ssh root@<vps-ip>
```

บน VPS:

```bash
# วิธีที่ 1: รันจาก git (recommended)
curl -fsSL https://raw.githubusercontent.com/wmmworld/joggy-picx/master/tools/deploy/bootstrap_vps.sh \
  | sudo bash

# วิธีที่ 2: clone แล้วรัน (ถ้าต้องการ review ก่อน)
git clone https://github.com/wmmworld/joggy-picx.git /tmp/joggy-bootstrap
sudo bash /tmp/joggy-bootstrap/tools/deploy/bootstrap_vps.sh
```

Script จะทำ:
- ✅ apt update + base packages (`git`, `ufw`, `fail2ban`, `certbot`, ...)
- ✅ สร้าง user `joggy` (sudo, docker group, SSH key from root)
- ✅ Install Docker Engine + Compose plugin
- ✅ ufw firewall (allow 22, 80, 443)
- ✅ fail2ban (sshd jail)
- ✅ Disable root SSH login
- ✅ สร้าง `/opt/joggy-picx` (chown joggy)

**Verify:** logout แล้ว `ssh joggy@<vps-ip>` ทำงานได้ + `docker ps` ไม่ permission error.

---

## 2. Deploy App

ในฐานะ `joggy@vps`:

```bash
# 2.1 Clone repo
cd /opt/joggy-picx
git clone https://github.com/wmmworld/joggy-picx.git .

# 2.2 Create production secrets
cp infra/env.production.template .env.production
chmod 600 .env.production
nano .env.production         # ← ใส่ค่าจริงทั้งหมด
```

> ⚠️ **SECRET_KEY** ต้อง 64 hex chars สร้างด้วย:
> `python3 -c "import secrets; print(secrets.token_hex(32))"`
> Production จะ fail-fast ถ้าเจอ `change-me-in-production`

```bash
# 2.3 Apply Alembic migrations against Supabase (one-time per migration set)
cd apps/backend
python3 -m venv .venv
source .venv/bin/activate
pip install uv==0.5.18
uv sync --no-dev
uv run alembic upgrade head
deactivate
cd /opt/joggy-picx

# 2.4 Place ONNX model (gitignored — must upload from dev box)
# จาก laptop:
scp apps/backend/models/yolov8n_bib.onnx joggy@<vps-ip>:/opt/joggy-picx/apps/backend/models/

# 2.5 Build + start services
cd infra
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 2.6 Verify services up
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=50 fastapi
```

ตอนนี้ทดสอบ HTTP (ยังไม่มี SSL):

```bash
curl -fsS http://127.0.0.1/healthz   # → ok
curl -fsS http://<vps-ip>/healthz    # → ok (from outside)
```

ถ้า healthz ตอบไม่ครบ → ดู logs `fastapi` หาสาเหตุ (มักเป็น .env ผิด / Supabase DATABASE_URL ผิด)

---

## 3. SSL — Let's Encrypt

### 3.1 Pre-flight

DNS ต้องชี้ที่ VPS แล้ว:

```bash
dig +short YOUR_DOMAIN          # ต้องตรง VPS IP
```

### 3.2 Bootstrap cert (one-time)

```bash
# ใช้ webroot mode — certbot เขียน challenge ลง /var/www/certbot
sudo mkdir -p /var/www/certbot
sudo certbot certonly --webroot \
    -w /var/www/certbot \
    -d YOUR_DOMAIN \
    --email YOUR_EMAIL \
    --agree-tos --no-eff-email
```

ผลที่ได้: cert อยู่ที่ `/etc/letsencrypt/live/YOUR_DOMAIN/{fullchain,privkey}.pem`

### 3.3 Activate HTTPS server block

```bash
cd /opt/joggy-picx
mv infra/nginx/conf.d/ssl-joggy.conf.disabled infra/nginx/conf.d/ssl-joggy.conf
sed -i "s/__YOUR_DOMAIN__/YOUR_DOMAIN/g" infra/nginx/conf.d/ssl-joggy.conf

# Restart nginx
cd infra
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart nginx
```

ทดสอบ:

```bash
curl -fsS https://YOUR_DOMAIN/healthz   # ✅
```

### 3.4 Auto-renew

certbot snap version จะ auto-renew อยู่แล้ว. ตรวจ:

```bash
sudo systemctl list-timers certbot.timer
sudo certbot renew --dry-run
```

หลัง renew ต้องบอก nginx ให้ reload cert — ตั้ง renewal hook:

```bash
sudo nano /etc/letsencrypt/renewal-hooks/post/reload-nginx.sh
```

เนื้อหา:
```bash
#!/usr/bin/env bash
cd /opt/joggy-picx/infra
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec nginx nginx -s reload
```

```bash
sudo chmod +x /etc/letsencrypt/renewal-hooks/post/reload-nginx.sh
```

### 3.5 Enable HSTS (after confirming HTTPS works)

แก้ `infra/nginx/conf.d/ssl-joggy.conf` — uncomment บรรทัด HSTS:

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
```

แล้ว `docker compose ... restart nginx`

⚠️ Once on, browsers refuse plain HTTP for 1 year — make sure ทดสอบ HTTPS เรียบร้อยก่อน

---

## 4. PDPA Retention Cron — Install systemd timer

```bash
sudo cp /opt/joggy-picx/infra/systemd/joggy-retention.* /etc/systemd/system/

# Adjust user in service file if not running app under user 'joggy'
sudo nano /etc/systemd/system/joggy-retention.service
# Verify: WorkingDirectory=/opt/joggy-picx/apps/backend
#         User=joggy
#         EnvironmentFile=/opt/joggy-picx/.env.production
```

⚠️ **EnvironmentFile path:** service ใช้ `/opt/joggy-picx/apps/backend/.env` เป็น default — เปลี่ยนเป็น `/opt/joggy-picx/.env.production` (path เดียวกับที่ docker-compose ใช้)

```bash
# Make python venv accessible at /opt/joggy-picx/.venv
cd /opt/joggy-picx/apps/backend
# (already set up in step 2.3)
ls -la .venv/bin/python   # should exist

# If venv lives under apps/backend, update ExecStart in service file:
#   ExecStart=/opt/joggy-picx/apps/backend/.venv/bin/python -m joggy.worker.retention

sudo systemctl daemon-reload
sudo systemctl enable --now joggy-retention.timer

# Verify
sudo systemctl list-timers joggy-retention.timer
sudo systemctl start joggy-retention.service   # manual run for smoke test
sudo journalctl -u joggy-retention.service -n 50 --no-pager
```

---

## 5. Full Smoke Test

### 5.1 Backend health

```bash
curl -fsS https://YOUR_DOMAIN/healthz                              # ok
curl -fsS https://YOUR_DOMAIN/docs                                  # OpenAPI page
```

### 5.2 Login dashboard

Browser → `https://YOUR_DOMAIN/` → login with Supabase user.

### 5.3 Pi upload test

บน Pi (ที่มี EVENT_TOKEN จาก dashboard):

```bash
curl -X POST https://YOUR_DOMAIN/ingest/photos?device_id=pi-001 \
  -H "Authorization: Bearer evt_xxxxx" \
  -F "file=@test.jpg"
# Expect: 202 Accepted with job_id
```

### 5.4 PDPA cron manual run

```bash
sudo systemctl start joggy-retention.service
sudo journalctl -u joggy-retention.service -n 30 --no-pager
```

ดู audit log ใน Supabase:
```sql
SELECT action, target_id, context, created_at
FROM audit_logs
WHERE actor_kind = 'system' AND action LIKE 'retention_%'
ORDER BY created_at DESC LIMIT 10;
```

---

## 6. Day-2 Operations

### Update deploy

```bash
cd /opt/joggy-picx
git pull
cd infra
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
# Watchtower will pick up new images on its next poll (5 min)
```

### View logs

```bash
# All services
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f --tail=100

# Specific service
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f fastapi
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f worker

# Retention cron history
sudo journalctl -u joggy-retention.service --since "1 week ago"
```

### Restart a single service

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml restart fastapi
```

### Database migrations on a running system

```bash
cd /opt/joggy-picx/apps/backend
source .venv/bin/activate
uv run alembic upgrade head
# Then restart fastapi (worker picks up via watchtower)
docker compose -f /opt/joggy-picx/infra/docker-compose.yml -f /opt/joggy-picx/infra/docker-compose.prod.yml restart fastapi
```

---

## 7. Backup / DR

| Asset | Location | Backup strategy |
|-------|----------|-----------------|
| Postgres (Supabase) | Supabase managed | Supabase daily backups (Pro plan); manual `pg_dump` weekly to local SSD |
| R2 photos | Cloudflare R2 | R2 has 30d soft-delete window built-in; configure object lifecycle |
| Redis | VPS volume `redis_data` | Ephemeral — RQ jobs only; loss = re-enqueue from audit log (DEV-3) |
| Code | GitHub | repo + tags |
| .env.production | VPS only | Manually back up to password manager (Bitwarden/1Password) |

### Manual Postgres backup

```bash
# จาก laptop
PGPASSWORD=$DB_PASSWORD pg_dump \
  -h aws-1-ap-southeast-1.pooler.supabase.com \
  -p 5432 -U postgres.YOUR_REF \
  -d postgres \
  -F c -f joggy-$(date +%F).dump
```

---

## 8. Rollback

```bash
cd /opt/joggy-picx
git log --oneline -10
git checkout <previous-good-sha>
cd infra
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

For DB schema rollback — careful, only if you're sure:

```bash
cd /opt/joggy-picx/apps/backend
uv run alembic downgrade -1
```

---

## 9. Monitoring (TODO Phase 5+ follow-up)

ตอนนี้ยังไม่มี dashboard — ใช้:

- `docker compose ... ps` → service state
- `journalctl -u joggy-retention.service` → cron health
- Supabase dashboard → DB metrics
- Cloudflare dashboard → R2 metrics + bandwidth
- Hetzner Cloud Console → CPU/mem graphs

Recommended next steps:
- **Discord webhook** สำหรับ:
  - Watchtower (new deployment)
  - systemd OnFailure (retention cron failed)
  - DEV-4 health widget (worker queue depth alert)
- **Uptime monitoring** — UptimeRobot ฟรี ping `/healthz` ทุก 5 นาที

---

## 10. Reference

- ADR-0001 Hosting (Hetzner CPX11)
- ADR-0004 PDPA retention
- ADR-0005 Watchtower auto-update
- `infra/systemd/README.md` — cron details
- `apps/backend/joggy/core/config.py` — env var list
- `tools/deploy/bootstrap_vps.sh` — bootstrap script source
