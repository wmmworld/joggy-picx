# Hetzner Setup — ARCHIVED

> ⚠️ **เอกสารนี้ถูก supersede แล้ว.**
> ใช้ **[docs/production-deploy.md](./production-deploy.md)** สำหรับ deploy production
>
> Runbook ใหม่ครอบคลุม:
> - VPS bootstrap (joggy user, Docker, ufw, fail2ban)
> - Production secrets (.env.production from `infra/env.production.template`)
> - docker-compose.prod.yml overlay (Supabase + R2 + healthchecks)
> - Nginx reverse proxy + Let's Encrypt SSL
> - PDPA retention systemd timer (ADR-0004)
> - Smoke test, backup, rollback, monitoring guide
>
> Original Phase 1 skeleton kept in git history (commit `<bootstrap>`).
