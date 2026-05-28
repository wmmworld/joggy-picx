<!-- Codex: runbook เตรียม Hetzner CPX11 สำหรับ Phase 1 deployment skeleton -->
# Hetzner CPX11 Setup Runbook

เอกสารนี้เป็น runbook สำหรับเตรียม VPS บน Hetzner ให้พร้อมรัน `infra/docker-compose.yml` ตามสถาปัตยกรรม Phase 1

## 1) Provision เครื่อง

1. สร้าง VM: `CPX11` (2 vCPU / 2 GB RAM / 40 GB SSD)
2. Region แนะนำ: เลือกใกล้ประเทศไทยที่สุด (เช่น `nbg1`/`hel1` แล้วแต่ latency)
3. OS: `Ubuntu 24.04 LTS`
4. เปิด Firewall เฉพาะพอร์ตจำเป็น:
   - `22/tcp` (SSH)
   - `80/tcp` (HTTP)
   - `443/tcp` (HTTPS, จะใช้เมื่อเพิ่ม TLS จริง)

## 2) Bootstrap server

```bash
# Codex: update package index และเครื่องมือพื้นฐาน
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg ufw git

# Codex: ติดตั้ง Docker Engine + Compose plugin
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker "$USER"
newgrp docker

docker --version
docker compose version
```

## 3) Clone repository + prepare env

```bash
# Codex: clone monorepo ไปยัง home ของ deploy user
git clone <YOUR_REPO_URL> joggy-picx
cd joggy-picx

# Codex: เตรียม env file สำหรับ compose (ห้าม commit)
cp .env.example .env 2>/dev/null || true
```

เติมค่าที่จำเป็นใน `.env` เช่น:
- `GHCR_USERNAME`
- `GHCR_TOKEN` (scope `read:packages`)
- ค่า runtime ที่ backend/worker จะใช้ใน Phase 2

## 4) GHCR login (สำหรับ Watchtower pull image)

```bash
# Codex: login registry เพื่อให้ watchtower pull private image ได้
echo "$GHCR_TOKEN" | docker login ghcr.io -u "$GHCR_USERNAME" --password-stdin
```

ตรวจว่ามีไฟล์ auth:
- `~/.docker/config.json`

## 5) Start services

```bash
# Codex: รัน services skeleton ตาม compose
cd infra
docker compose up -d --build
docker compose ps
```

service ที่ต้องเห็น:
- `nginx`
- `fastapi`
- `redis`
- `worker`
- `watchtower`

## 6) Smoke checks

```bash
# Codex: ตรวจสุขภาพ nginx endpoint
curl -fsS http://127.0.0.1/healthz

# Codex: ตรวจ logs เบื้องต้น
docker compose logs --tail=100 nginx fastapi worker redis watchtower
```

## 7) Operational notes

- Watchtower poll ทุก 5 นาทีตาม ADR-0005
- เปิด auto-update เฉพาะ container ที่มี label:
  - `com.centurylinklabs.watchtower.enable=true`
- เมื่อ production readiness สูงขึ้น ให้เพิ่ม:
  - TLS (Caddy/Nginx + Let's Encrypt)
  - backup policy ของ Redis/Postgres
  - metrics + alerting

## 8) Rollback quick guide

1. pin image เป็น SHA tag (`main-<sha>`) ใน `docker-compose.yml`
2. `docker compose up -d`
3. ตรวจ `docker compose ps` และ logs อีกครั้ง
