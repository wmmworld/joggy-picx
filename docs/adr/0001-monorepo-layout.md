# ADR-0001 — ใช้ Monorepo เดียวสำหรับทุก codebase

- **Status:** Accepted
- **Date:** 2026-05-28
- **Deciders:** CEO + Claude (Tech Lead)
- **Related:** [DECISIONS.md#D-009](../../DECISIONS.md)

---

## 1. Context

โปรเจก Joggy-PicX มี 3 codebase หลักที่ต้องอยู่ในระบบเดียวกัน:

1. **Backend** — FastAPI + Python-RQ Worker + AI Pipeline (Python)
2. **Frontend** — Next.js dashboard (TypeScript)
3. **Edge** — Raspberry Pi watchdog uploader (Python)
4. *(อนาคต)* Mobile app — Expo/Native/PWA

ทีมพัฒนา = Solo dev (CEO) + AI 4 ตัว (Claude, Codex, Cursor, Antigravity) ที่ทำงาน parallel
เป้าหมาย: AI ทุกตัวอ่าน context จากที่เดียว, ส่ง handoff ระหว่างกันได้ง่าย, share types ข้าม language ได้

## 2. Decision

ใช้ **Monorepo เดียว** ที่ root `Joggy-PicX/` พร้อม layout:

```
Joggy-PicX/
├── apps/
│   ├── backend/      # FastAPI + Worker (Python)
│   ├── frontend/     # Next.js (TypeScript)
│   └── edge/         # Pi watchdog uploader (Python)
├── packages/
│   └── shared/       # OpenAPI types + constants ที่ใช้ข้าม app
├── infra/
│   ├── docker-compose.yml
│   ├── nginx/
│   └── pi/           # Pi provisioning scripts
├── docs/
│   ├── adr/          # Architecture Decision Records
│   └── ...           # คู่มืออื่นๆ
├── .github/workflows/    # CI/CD (path-filtered)
└── (root docs)       # CLAUDE.md, AGENTS.md, ARCHITECTURE.md, PROGRESS.md, DECISIONS.md, CHANGELOG.md
```

## 3. Alternatives Considered

### Option B — Multi-repo (3 repo แยก)
- ✅ แต่ละ repo เล็ก, deploy แยกชัด, permission แยกได้
- ❌ Sync types/schema ข้าม repo เจ็บ — ต้องใช้ npm package + publish
- ❌ PROGRESS.md ต้อง sync 3 repo — AI handoff ยาก
- ❌ Cross-cutting change ต้อง 3 PR

### Option C — Hybrid (Backend+Edge รวม, Frontend แยก)
- ✅ Frontend deploy Vercel ง่ายขึ้น
- ❌ ยังต้อง sync types ข้าม repo
- ❌ ความซับซ้อนของทั้ง 2 option ผสม

## 4. Consequences

### Positive
- AI 4 ตัวอ่าน context จากที่เดียว — โดยเฉพาะ `PROGRESS.md` กลาง
- Cross-cutting change = 1 commit (เช่น เพิ่ม field ใน Photo schema กระทบ backend + frontend + edge)
- Shared types ใน `packages/shared/` — generate จาก OpenAPI spec ของ FastAPI
- Vercel deploy Next.js จาก subfolder ทำได้ปกติ (`Root Directory = apps/frontend`)

### Negative / Tradeoffs ที่ต้องรับ
- CI/CD ต้อง config `paths:` filter ให้ดี — แก้ frontend ไม่ต้อง rebuild backend
- Python apps 2 ตัว (backend, edge) ใช้ pyproject.toml แยก — workspace ของ Python ยังไม่ standard เท่า JS
- ขนาด repo จะโต — ต้องระวัง model weights/datasets ไม่ commit (ใช้ Git LFS หรือเก็บที่ R2 แทน)

### Reversibility
- Hard-to-reverse — ถ้าเปลี่ยนเป็น multi-repo ทีหลัง ต้อง split history, redirect import, แยก CI
- **เพราะฉะนั้น ADR นี้สำคัญ** — ตัดสินใจตอนนี้ดีกว่ามาตัดสินใจตอน Phase 3

## 5. Rules ที่ตามมาจาก decision นี้

1. ห้าม commit binary ใหญ่ — model weights, datasets เก็บที่ R2 + download ตอน build
2. Python deps ของ `backend/` และ `edge/` แยก pyproject.toml กัน (ต่าง runtime, ต่าง deps)
3. `packages/shared/` generate อัตโนมัติจาก OpenAPI ของ backend — ไม่ใช่เขียนมือ
4. GitHub Actions ต้องใช้ `paths:` filter ทุก job เพื่อลด CI cost
5. Vercel project = `apps/frontend/`, Root Directory ต้องตั้งถูกใน Vercel Dashboard
