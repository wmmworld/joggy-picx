# AGENTS.md — กฎกลางสำหรับ AI ทุกตัวในทีม Joggy-PicX

> **Single Source of Truth** สำหรับ Claude Code / Codex / Cursor / Antigravity / Qwen
> ทุก AI ที่ commit โค้ดเข้าโปรเจกนี้ ต้องอ่าน + บังคับใช้เอกสารฉบับนี้ครบทุกข้อ
> เขียนเป็นภาษาไทย ยกเว้น Code / Tech Terms

---

## 1. ภาพรวมโปรเจก

**Joggy-PicX** — ระบบถ่ายรูปนักวิ่งมาราธอนอัตโนมัติ
- Canon EOS RP → WiFi FTP → Raspberry Pi 5 → Cloudflare R2
- Hetzner CPX11 (Docker Compose all-in-one): vsftpd + Redis + Python-RQ + FastAPI + AI Worker + Nginx
- Supabase free tier (PostgreSQL + pgvector)
- Next.js + Vercel (dashboard)
- AI (CPU-only): YOLOv8-nano + PaddleOCR + InsightFace
- Scale: ~1,000 รูป/งาน, ~1,000 นักวิ่ง, งบ cloud ~$6–7/เดือน

รายละเอียดเต็มดูที่ [ARCHITECTURE.md](ARCHITECTURE.md)

---

## 2. ทีมและบทบาท

| AI | บทบาท | งานหลัก |
|---|---|---|
| **Claude Code** | Tech Lead + Lead Architect | Backend, Architecture, Integration, ตัดสินใจ final |
| **Codex** | VP Engineering | Backend หนัก, สานต่อเมื่อ Claude ติด limit |
| **Cursor** | Frontend Specialist | Next.js dashboard, Mobile UI |
| **Antigravity** | Flex Agent | Parallel tasks, รับงานแทนทุกตัวได้ |
| **Qwen** | External Advisor | Review เท่านั้น ไม่อยู่ใน dev team |
| **CEO** | เจ้าของโปรเจก | ทดสอบ รายงาน bug ตัดสินใจขั้นสุดท้าย |

**หลักการสำคัญ:** AI 4 ตัวทำงาน **parallel** ไม่ใช่ sequential
- Claude + Codex ทำ backend พร้อมกันได้
- Cursor + Antigravity ทำ frontend / parallel tasks พร้อมกันได้
- ก่อนเริ่มงาน → ดูตาราง Active Tasks ใน [PROGRESS.md](PROGRESS.md) ป้องกันชนงาน

---

## 3. Engineering Standards (บังคับใช้ทุกครั้ง)

### 3.1 ก่อนเขียนโค้ด — บังคับ

1. อ่าน [PROGRESS.md](PROGRESS.md), [DECISIONS.md](DECISIONS.md), [ARCHITECTURE.md](ARCHITECTURE.md)
2. วิเคราะห์ architecture ปัจจุบันก่อนเสมอ — ห้ามเดา
3. อธิบายว่าจะแก้อะไร ทำไม ผลกระทบคืออะไร
4. ถ้าพบ design ที่ดีกว่า → เสนอทันที ก่อนเขียนโค้ด
5. อธิบาย tradeoff + scalability impact
6. ถ้างานเปลี่ยน DB schema / API contract → ต้องผ่าน Claude (Tech Lead) ก่อน

### 3.2 หลังเขียนโค้ด — บังคับ

1. สรุปสิ่งที่เปลี่ยนเป็นภาษาไทยให้ CEO
2. แจ้งไฟล์ที่แก้ไขทั้งหมด (relative path)
3. แจ้งผลกระทบ + performance impact
4. อัปเดต [PROGRESS.md](PROGRESS.md) ทันที — ห้ามค้าง
5. อัปเดต [CHANGELOG.md](CHANGELOG.md) ทันที
6. ใส่คอมเม้นต์ระบุตัวตนทุก block ที่แตะ:
   - `# Claude: <คำอธิบาย>` (Python)
   - `// Codex: <คำอธิบาย>` (TS/JS)
   - `// Cursor: <คำอธิบาย>` (Frontend)
   - `# Antigravity: <คำอธิบาย>` (Misc)

### 3.3 การแก้ Bug — บังคับระบุ

- Bug คืออะไร (สิ่งที่ผู้ใช้/ระบบเห็น)
- สาเหตุ (root cause ไม่ใช่ symptom)
- วิธีแก้ + ทำไมแก้แบบนี้
- ผลกระทบ + regression risk

### 3.4 การ Refactor — บังคับระบุ

- เหตุผลที่ต้อง refactor
- Architecture ก่อน vs หลัง
- Backward compatibility (เปลี่ยน API contract หรือไม่)
- Migration path (ถ้ามี)

### 3.5 ห้ามเด็ดขาด

- ❌ Dead code (ไม่ comment ทิ้ง ลบเลย)
- ❌ Duplicate logic (extract เป็น function/module)
- ❌ Temporary hack ที่ไม่มี TODO + วันที่จะแก้
- ❌ ลืม comment ระบุตัวตน
- ❌ ลืมอัปเดต PROGRESS.md / CHANGELOG.md
- ❌ Commit `.env`, credentials, ไฟล์ขนาดใหญ่ (model weights, datasets)
- ❌ แก้ DB schema โดยไม่มี migration file
- ❌ Skip pre-commit hook / lint / test
- ❌ ใช้ `print()` ใน production code — ใช้ `logger`

### 3.6 หลักการ Production-Grade

- Readability + Consistency + Documentation สูงสุด
- AI ตัวอื่นต้องอ่านแล้วเข้าใจได้ทันทีโดยไม่ต้องถาม
- รักษา backward compatibility + database integrity
- Error handling ที่ขอบเขตระบบ (user input, external API) เท่านั้น
- Type hint ครบ (Python 3.11+ syntax) / TypeScript strict mode (Frontend)
- Test coverage: critical path 100%, อื่นๆ ~70%

### 3.7 ภาษาที่ใช้

| สิ่ง | ภาษา |
|---|---|
| เอกสารทั้งหมด (.md) | ไทย |
| Code / Identifier / File name | อังกฤษ |
| Inline comment | ไทย (TODO/FIXME/NOTE ใช้อังกฤษ) |
| Commit message | อังกฤษ — Conventional Commits |
| Error message ให้ user | ไทย |
| Log message ภายใน | อังกฤษ |

---

## 4. Handoff Protocol — เมื่อ AI ติด Limit

### 4.1 ก่อนหยุด AI ที่ติด limit ต้อง:

1. อัปเดต `## 🔄 Active Handoff` ใน [PROGRESS.md](PROGRESS.md) ด้วย:
   - Task name + AI ที่ทำค้าง
   - ไฟล์ที่กำลังแก้ + บรรทัดล่าสุด
   - Checkpoint: สิ่งที่ทำเสร็จแล้ว
   - Next steps: step-by-step ที่เหลือ
   - Decisions ที่เพิ่งตัดสินใจ (ถ้ามี)
2. Commit หรือ stash โค้ดที่ค้าง — message: `[WIP][<ai>-handoff] <task>`
3. ระบุชัดว่าให้ใครรับช่วงต่อ:
   - Backend หนัก → Codex
   - Architecture / Integration → Claude (รอ session ใหม่)
   - Frontend → Cursor
   - Parallel / Research / Flex → Antigravity

### 4.2 AI ที่รับ handoff ต่อต้อง:

1. อ่าน `Active Handoff` ใน PROGRESS.md
2. อ่านไฟล์ที่ระบุไว้ทั้งหมด
3. ทำงานต่อตาม Next steps
4. เมื่อเสร็จ → เคลียร์ `Active Handoff` + อัปเดต CHANGELOG

---

## 4.3 Model Tier Guide (ใช้กับ Active Tasks ใน PROGRESS.md)

ก่อนเริ่ม task ทุกครั้ง AI / CEO ต้องระบุ Tier + Model ในตาราง Active Tasks เพื่อประหยัด token

| Tier | งานที่เหมาะ | ตัวอย่าง Model |
|---|---|---|
| **A — Frontier** | Architecture, complex refactor, security review, multi-file reasoning, debug ลึก | `claude-opus-4-7`, `gpt-5-pro`, `o3-pro`, `gemini-3-pro-thinking` |
| **B — Balanced** | Feature implementation, schema design, normal coding, code review, multi-source synthesis | `claude-sonnet-4-6`, `gpt-5`, `gemini-3-pro` |
| **C — Fast/Cheap** | Scaffold, file rename, boilerplate, research summary, lint fix, config | `claude-haiku-4-5`, `gpt-5-mini`, `o4-mini`, `gemini-3-flash` |

**Rules:**
1. เริ่ม Tier C เสมอถ้างานเป็น pure scaffold/boilerplate
2. งานที่ต้อง "judge tradeoff" → Tier A อย่างน้อยตอน plan
3. Implementation หลัง plan ชัด → ลด tier ลง 1 ระดับได้
4. ติด debug → อัป tier ขึ้น (Frontier เจอ root cause เร็วกว่า)
5. ห้ามใช้ Frontier ตอน boilerplate — เสีย token ฟรี

---

## 5. การใช้ PROGRESS.md

[PROGRESS.md](PROGRESS.md) คือ heartbeat ของทีม — ทุก AI อ่านไฟล์นี้แล้วทำงานต่อได้ทันที

โครงสร้าง:
1. **Current Phase** — Phase / Day ปัจจุบัน
2. **Active Tasks** — ตารางว่า AI ตัวไหนทำอะไรอยู่ (กันชนงาน)
3. **Active Handoff** — งานค้างที่ต้องรับช่วงต่อ
4. **Milestones** — milestone แต่ละ phase
5. **Backlog** — สิ่งที่ยังไม่ได้ทำทั้งหมด
6. **Done Log** — งานที่เสร็จแล้ว (เรียงตามเวลา)

**กฎ:** ก่อนเริ่มงาน → ขีดชื่อตัวเองในตาราง Active Tasks; เสร็จแล้ว → ย้ายไป Done Log

---

## 6. การตัดสินใจสำคัญ

- Decision ที่ Hard-to-Reverse → บันทึกใน [DECISIONS.md](DECISIONS.md) + สร้าง ADR ใน `docs/adr/`
- Decision ที่กระทบ multi-AI (เช่น เปลี่ยน DB schema, เปลี่ยน API contract) → ต้องผ่าน Claude (Tech Lead) ก่อน
- Decision เล็ก (เลือก library minor, naming) → AI ผู้รับผิดชอบตัดสินใจเองได้ แต่ต้อง comment เหตุผล

---

## 7. Skill ที่ต้องใช้ตามสถานการณ์

| สถานการณ์ | Skill |
|---|---|
| เริ่ม Feature ใหม่ / Phase ใหม่ | `superpowers:brainstorming` |
| มี plan แล้วต้องเขียนเอกสาร | `superpowers:writing-plans` |
| Stress-test plan + sharpen terminology | `grill-with-docs` |
| เขียน Feature / Bugfix | `superpowers:test-driven-development` |
| เจอ Bug / Test Failure | `superpowers:systematic-debugging` |
| ก่อน claim ว่าเสร็จ | `superpowers:verification-before-completion` |
| ขอ review โค้ดตัวเอง | `superpowers:requesting-code-review` |
| มีงาน parallel 2+ tasks independent | `superpowers:dispatching-parallel-agents` |

---

## 8. ความเสี่ยงที่ AI ทุกตัวต้องระวัง

1. **Canon FTP ข้าม WAN ไม่ได้** → Raspberry Pi 5 เป็น REQUIREMENT ไม่ใช่ optional
2. **Bib OCR accuracy ต่ำในสนามจริง** → ต้องมี fallback ไป face re-ID ตลอด
3. **InsightFace บน Linux** อาจมีปัญหา dependency (onnxruntime, libgl) — pin version ทุกตัว
4. **กล้อง + Pi** ต้องต่อ dummy battery ตลอดงาน (อายุงาน 4–6 ชม.)
5. **NTP sync** ทุก device ต้องตรงกันก่อนเริ่มงาน มิฉะนั้น cross-checkpoint re-ID พัง
6. **PDPA** — face embedding ต้องได้ consent + auto-delete หลัง 30 วัน

---

## 9. PDPA & Security Baseline

ดูรายละเอียดเต็มที่ [ADR-0004 — PDPA Retention Policy](docs/adr/0004-pdpa-retention-policy.md)

**System boundary (สำคัญ!):**
- Joggy-PicX = closed/internal system → runner ไม่ login → ไม่มี consent UI ในระบบนี้
- Consent อยู่ฝั่ง External Partner (เช่น race-result.asia) ตอนนักวิ่งสมัครงาน
- Right to Erasure ใช้ผ่าน Partner → เรียก `DELETE /v1/erasure` ของ Joggy-PicX

**Retention (D-014):**
- รูปต้นฉบับ: 30 วันหลังจบงาน (extend +30 วันได้ 1 ครั้งผ่าน admin)
- Face embedding: 7 วันหลังจบงาน (สั้นกว่ารูป)
- Metadata: เก็บถาวร anonymized (ลบ link bib→identity)
- Opt-in 1 ปี ผ่าน flag ที่ partner ส่งมาตอน register runner
- Right to Erasure ผ่าน Partner API (≤24 ชม.)

**Baseline rules:**
- **ห้าม** สร้าง consent UI ใน Joggy-PicX สำหรับ runner — consent อยู่ฝั่ง partner
- ห้าม implement runner-facing login / signup / dashboard ใน Joggy-PicX
- Face embedding (512-dim) = sensitive biometric data → encrypt at rest + auto-delete
- API key / R2 token / Supabase secret → environment variable เท่านั้น ห้าม commit
- Public endpoint ต้องมี rate limit
- Log ห้ามมี PII plain text
- Hard delete เท่านั้น (ไม่ใช่ soft delete) — PDPA ม.30
- ทุก table ที่มี personal data ต้องมี `retention_until: TIMESTAMP`
- R2 lifecycle rule ตั้ง 35 วัน buffer (เผื่อ cron พลาด)

---

## 10. Definition of Done

งานนับว่า "เสร็จ" ก็ต่อเมื่อ:

- [ ] Code ผ่าน lint + type check
- [ ] Test ที่เกี่ยวข้องผ่านทั้งหมด
- [ ] PROGRESS.md อัปเดตแล้ว
- [ ] CHANGELOG.md อัปเดตแล้ว
- [ ] Comment ระบุตัวตน AI ครบทุก block
- [ ] CEO รับทราบสรุปภาษาไทยแล้ว
- [ ] ไม่มี Dead code / Temporary hack ที่ไม่มี TODO + วันที่
