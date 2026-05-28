# ADR-0005 — CI/CD: GitHub Actions + GHCR + Watchtower

- **Status:** Accepted
- **Date:** 2026-05-28
- **Deciders:** CEO + Claude (Tech Lead)
- **Related:** [DECISIONS.md#D-016](../../DECISIONS.md), [ADR-0001 (Monorepo)](0001-monorepo-layout.md), [D-001 (Hetzner CPX11)](../../DECISIONS.md)

---

## 1. Context

โปรเจก Joggy-PicX เป็น monorepo มี 3 apps + shared package:
- `apps/backend/` (FastAPI + Worker, Python, → VPS Docker)
- `apps/frontend/` (Next.js, TypeScript, → Vercel)
- `apps/edge/` (Pi watchdog, Python, → Raspberry Pi 5 manual deploy)
- `packages/shared/` (TypeScript types generated จาก OpenAPI)

ข้อจำกัด:
- งบรวม cloud ~$6-7/เดือน → CI/CD ต้องฟรีหรือถูกมาก
- Private repo (มี secrets, biometric model weights)
- AI 4 ตัวต้องอ่าน workflow ในโค้ดได้ (ไม่ใช่ GUI-only CI)
- Edge (Pi) อยู่กลางสนาม → deploy ก่อนงานเท่านั้น ไม่ใช่ auto

GitHub Actions free tier: **2,000 นาที/เดือน** (private)
GHCR (GitHub Container Registry): **ฟรี unlimited** สำหรับ private package
Watchtower: open-source, lightweight (~20 MB) container ที่ poll image registry และ recreate container เมื่อมี image ใหม่

## 2. Decision

### 2.1 CI: GitHub Actions พร้อม path filter

```
.github/workflows/
├── ci-backend.yml       paths: ['apps/backend/**', 'packages/shared/**']
│   └─ ruff + mypy + pytest + docker build/push GHCR
├── ci-frontend.yml      paths: ['apps/frontend/**', 'packages/shared/**']
│   └─ biome + tsc + vitest (Vercel deploy เอง)
├── ci-edge.yml          paths: ['apps/edge/**']
│   └─ ruff + mypy + pytest + build wheel artifact (เก็บไว้ download ไป Pi)
├── ci-shared.yml        paths: ['packages/shared/**']
│   └─ generate types + check no breaking change
└── adr-link-check.yml   schedule: weekly  # ตรวจ link ใน docs/adr/
```

Cache strategy (ลด build time):
- Python: `uv cache` ผ่าน `actions/cache` keyed on `uv.lock`
- Node: `pnpm store` ผ่าน `actions/cache` keyed on `pnpm-lock.yaml`
- Docker: BuildKit layer cache ใน registry (`type=registry`)

### 2.2 Registry: GitHub Container Registry (GHCR)

Image naming:
- `ghcr.io/<owner>/joggy-picx-backend:main-<sha>`
- `ghcr.io/<owner>/joggy-picx-backend:main-latest`
- `ghcr.io/<owner>/joggy-picx-worker:main-<sha>`
- `ghcr.io/<owner>/joggy-picx-worker:main-latest`

Tag policy:
- Production VPS pull tag `:main-latest` (Watchtower tracks)
- Roll back ใช้ tag `:main-<sha>` (manual)

### 2.3 Deployment

| Service | Method | Trigger |
|---|---|---|
| Frontend (Vercel) | Vercel auto deploy จาก GitHub | git push main → preview/prod |
| Backend + Worker (VPS) | Watchtower poll GHCR ทุก 5 นาที | image ใหม่ → recreate container |
| Edge (Pi) | Manual via Ansible playbook | ก่อนแต่ละงาน (ไม่ใช่ auto) |

Watchtower config (docker-compose):
```yaml
watchtower:
  image: containrrr/watchtower
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
    - ~/.docker/config.json:/config.json:ro  # auth GHCR
  command:
    - --interval=300            # 5 นาที
    - --cleanup                  # ลบ image เก่า
    - --label-enable             # update เฉพาะ container ที่มี label
    - --rolling-restart
  restart: unless-stopped
```

เฉพาะ container ที่มี label `com.centurylinklabs.watchtower.enable=true` จะถูก update

## 3. Alternatives Considered

### Option A — GHA + Vercel + manual SSH deploy
- ✅ Simple, ใช้กันเยอะ
- ❌ Manual deploy = human error + slow
- ❌ AI ตัวที่รับ handoff ต้องรู้ SSH workflow

### Option B — GHA self-hosted runner บน VPS เดียวกัน
- ✅ ไม่จำกัด GHA minute
- ❌ กิน RAM VPS (~200 MB) — เราเหลือแค่ ~750 MB
- ❌ Security ปัญหา (untrusted PR code รันบน production VPS)

### Option D — Self-hosted CI (Drone / Gitea Actions)
- ✅ Custom เต็มที่
- ❌ เพิ่ม service maintenance, overkill

## 4. Consequences

### Positive
- ฟรี — GHA 2k นาที + GHCR + Vercel + Watchtower เป็น OSS
- Zero-touch deploy backend/worker → ลด human error
- Path filter ลด build time + ประหยัด GHA minute (estimate 5-10 นาที/PR)
- Workflow checked in → AI ทุกตัวอ่าน + debug ได้
- Vercel preview deploy automatic — review frontend PR ง่าย

### Negative / Tradeoffs ที่ต้องรับ
- Watchtower auto-pull → ต้อง pin image tag/digest ดี
  - **Mitigation:** ใช้ `:main-<sha>` ที่ pin, label enable เฉพาะ container ที่ต้องการ
- 2,000 GHA นาที/เดือน — ถ้าเกิน ต้องอัป GitHub Pro ($4/เดือน, 3k นาที)
  - **Mitigation:** Cache aggressive, path filter เข้มข้น, dedupe job
- Watchtower poll 5 นาที = deploy delay สูงสุด 5 นาที
  - **Mitigation:** acceptable สำหรับ scale ปัจจุบัน; อนาคตใช้ webhook trigger ได้
- Edge (Pi) manual deploy → ต้องมี Ansible playbook + checklist ก่อนงาน
  - **Mitigation:** เขียน playbook ใน `infra/pi/` + runbook ใน `docs/`

### Reversibility
- Reversible — workflows + Watchtower config เปลี่ยนได้ตลอด
- ถ้าโตเกิน → ย้ายเป็น self-hosted runner หรือ Argo CD ได้

## 5. Rules ที่ตามมาจาก decision นี้

1. ทุก service ที่ deploy ผ่าน Watchtower **ต้อง** ใส่ label `com.centurylinklabs.watchtower.enable=true`
2. Image tag policy: `main-<sha>` (immutable) + `main-latest` (rolling) — Watchtower track `main-latest`
3. PR ต้องผ่าน CI ก่อน merge (branch protection ใน GitHub)
4. Secrets ใช้ GitHub Secrets เท่านั้น — ห้าม commit
5. GHCR pull token บน VPS = scope `read:packages` เท่านั้น
6. Vercel project root directory = `apps/frontend`
7. Edge deploy:
   - ใช้ Ansible playbook ใน `infra/pi/`
   - Checksum verify ก่อนติดตั้ง (SHA256 จาก CI artifact)
   - Pi เก็บ rollback wheel เวอร์ชันก่อนหน้า
8. GHA minute budget alert ที่ 80% (1,600 นาที) → ทำ optimize cache
