<!-- Codex: ดัชนีเอกสารหลักสำหรับเริ่มงานใน monorepo -->
# Joggy-PicX

ระบบถ่ายรูปนักวิ่งมาราธอนอัตโนมัติ (Phase 1 skeleton)

## เริ่มอ่านจากตรงนี้

- [AGENTS.md](AGENTS.md) — กฎกลางการทำงานของ AI team
- [CONTEXT.md](CONTEXT.md) — glossary domain
- [DECISIONS.md](DECISIONS.md) — decision log (D-xxx)
- [ARCHITECTURE.md](ARCHITECTURE.md) — architecture overview
- [PROGRESS.md](PROGRESS.md) — active tasks / heartbeat
- [CHANGELOG.md](CHANGELOG.md) — changelog กลาง

## โครงสร้างหลัก

- `apps/backend` — FastAPI + worker package skeleton
- `apps/frontend` — Next.js internal dashboard
- `apps/edge` — Raspberry Pi uploader skeleton
- `packages/shared` — shared/generated types placeholder
- `infra` — Docker Compose, Nginx, Pi provisioning skeleton
- `docs` — ADRs, schema, runbooks
