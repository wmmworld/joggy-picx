# Joggy-PicX VPS systemd Units

ไฟล์ systemd สำหรับติดตั้งบน VPS (Hetzner CPX11).

## Files

| Unit | บทบาท |
|------|-------|
| `joggy-retention.service` | One-shot — รัน `python -m joggy.worker.retention` (3 PDPA cron tasks) |
| `joggy-retention.timer`   | Daily trigger ที่ 00:00 ICT — fire service ด้านบน |

> Backend FastAPI / RQ worker / Redis / Postgres รันใน Docker Compose
> (`infra/docker-compose.yml`) ไม่ผ่าน systemd. Retention cron แยกเป็น
> systemd timer บน host เพราะต้องการ:
> - reliability ระดับ OS (timer ไม่ตายตาม container)
> - log routing ผ่าน `journalctl` (ไม่ผูกกับ Docker log driver)
> - alerting แบบ standard (OnFailure=)

---

## Installation (บน Hetzner VPS)

```bash
# 1. Copy units
sudo cp infra/systemd/joggy-retention.* /etc/systemd/system/

# 2. Reload systemd
sudo systemctl daemon-reload

# 3. Enable + start timer (service จะถูก trigger โดย timer)
sudo systemctl enable --now joggy-retention.timer

# 4. ยืนยัน
sudo systemctl status joggy-retention.timer
sudo systemctl list-timers joggy-retention.timer
```

## ทดสอบ manual

```bash
# รัน service ทันทีไม่ต้องรอ timer
sudo systemctl start joggy-retention.service

# ดู output
sudo journalctl -u joggy-retention.service -n 50 --no-pager
```

## Schedule

```
OnCalendar=*-*-* 00:00:00 Asia/Bangkok
```

- ฟangลัง midnight ICT ทุกวัน (= 17:00 UTC ของวันก่อนหน้า)
- `Persistent=true` → ถ้า VPS off ตอน 00:00 จะรัน catch-up ทันทีหลัง boot
- `RandomizedDelaySec=300` → jitter ไม่เกิน 5 นาที (กัน load spike ตรง 00:00 พอดี)

## Monitoring

```bash
# ดู log ของ runs ทั้งหมด
journalctl -u joggy-retention.service --since "1 week ago" --no-pager

# ดู timer schedule
systemctl list-timers joggy-retention.timer

# Audit log (ใน Postgres)
SELECT action, target_id, context, created_at
FROM audit_logs
WHERE actor_kind = 'system'
  AND action LIKE 'retention_%'
ORDER BY created_at DESC
LIMIT 50;
```

## Alerts (TODO Phase 5 follow-up)

- ตอนนี้ failure → exit code 1 → systemd marks unit failed
- รอ Phase 5 wire `OnFailure=` → Discord webhook หรือ email
- ดู ADR-0004 rule #2 "ห้าม fail silently"
