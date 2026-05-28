# ADR-0003 — Single AI Worker Process บน VPS (ไม่ใช่ multi-worker)

- **Status:** Accepted *(Revised 2026-05-28 — RAM budget corrected, see section 6)*
- **Date:** 2026-05-28
- **Deciders:** CEO + Claude (Tech Lead)
- **Related:** [DECISIONS.md#D-013](../../DECISIONS.md), [D-001 (Hetzner CPX11)](../../DECISIONS.md), [D-004 (CPU-only AI)](../../DECISIONS.md)

---

## 1. Context

VPS = Hetzner CPX11 = **2 vCPU + 2 GB RAM**

AI pipeline ต้อง load model ทั้ง 3 ตัวเข้า memory:
- YOLOv8-nano + PaddleOCR + InsightFace (buffalo_s) = **~900 MB ต่อ process**

Stack ที่ต้อง share RAM 2GB:
- Nginx ~30 MB
- FastAPI ~150 MB
- Redis ~20 MB
- AI Worker ~900 MB (1 process)
- vsftpd / kernel / overhead ~150 MB
- **รวม ~1.25 GB → เหลือ ~750 MB buffer**

Workload จริง:
- งาน 1 ครั้ง = ~1,000 รูป / 4–6 ชม. = **เฉลี่ย ~3 รูป/นาที**
- Pipeline 1 รูป = ~2–5 วินาที (CPU-bound)
- 1 worker × 5s/รูป → throughput **12 รูป/นาที** (4× ของ load จริง)

## 2. Decision

ใช้ **1 RQ worker process ใน 1 container** ที่ load model ครั้งเดียวตอน boot

```yaml
# docker-compose.yml (excerpt)
services:
  worker:
    image: joggy-picx-worker
    restart: unless-stopped
    mem_limit: 1200m            # cap กัน OOM
    command: rq worker default
    # rq worker = PID 1 (single process, ไม่มี supervisor)
```

Model preload pattern:
```python
# worker.py — Claude: load model ครั้งเดียวตอน boot ลด latency
yolo = YOLO("yolov8n.pt")
ocr  = PaddleOCR(lang="en")
face = FaceAnalysis(name="buffalo_s")

def process_photo(photo_id: str) -> None:
    # ใช้ model ที่ preload แล้ว
    ...
```

## 3. Alternatives Considered

### Option B — Multi-worker (2 RQ processes ใน 1 container)
- ✅ Throughput 2× = 24 รูป/นาที
- ❌ **RAM ชน 2GB** → 2 × 900MB model = 1.8GB + system stack ~350MB = OOM
- ❌ Throughput เกินจำเป็น (load จริง 3 รูป/นาที)

### Option C — Multi-container scale=2
- ✅ Isolation ดี, restart แยกได้
- ❌ RAM ปัญหาเดียวกับ Option B
- ❌ Container overhead เพิ่ม

### Option D — Process pool ที่ preload model + dispatcher
- ✅ Restart AI process ได้โดยไม่กระทบ queue
- ❌ Complex มาก สำหรับ scale ปัจจุบัน
- ❌ IPC overhead, debug ยาก
- ❌ Overkill ที่ 3 รูป/นาที

## 4. Consequences

### Positive
- RAM budget ปลอดภัย (~750 MB buffer)
- ดีบักง่าย — 1 worker, 1 log stream
- Migration path ชัดเจน — ถ้าโตค่อยอัปเป็น CPX21 (4 vCPU/4GB) แล้วเป็น Option C

### Negative / Tradeoffs ที่ต้องรับ
- ถ้า worker crash → queue ค้าง
  - **Mitigation:** Docker `restart: unless-stopped` + RQ job timeout + retry + dead letter queue
- ไม่มี parallelism ใน worker
  - **Mitigation:** ที่ scale 3 รูป/นาที ไม่ต้องการ parallelism
- Spike เล็กน้อย (เช่น 20 รูปใน 30 วินาที) → queue สะสม ~1.5 นาที
  - **Mitigation:** Async UX — นักวิ่งดูรูปหลังงานจบ ไม่ใช่ realtime

### Reversibility
- **Reversible ระดับกลาง** — แก้ docker-compose เพิ่ม replica/worker ได้ตลอด แต่ต้องอัป VPS RAM ก่อน
- **เพราะฉะนั้น decision นี้ตามมาด้วย "ห้ามเพิ่ม model หนักขึ้นโดยไม่วัด RAM ใหม่"**

## 5. Rules ที่ตามมาจาก decision นี้

1. AI Worker container ต้อง set `mem_limit` ใน docker-compose (กัน OOM ลาม service อื่น)
2. Model ต้อง preload ตอน boot — ห้าม lazy load ใน job function (slow + memory fragmentation)
3. ถ้าจะเพิ่ม AI model ใหม่ (เช่น pose estimation) → ต้อง **วัด RAM ใหม่ + บันทึก** ก่อน merge
4. Health check ต้องตรวจ:
   - Redis reachable
   - Worker heartbeat (RQ built-in: `Worker.last_heartbeat`)
   - Memory usage <85%
5. ถ้าโตเกิน ~5,000 รูป/งาน → trigger upgrade VPS + revisit ADR นี้

---

## 6. Revision — RAM Budget Correction (2026-05-28)

> **Source:** [docs/dependency-check.md](../../docs/dependency-check.md) — Antigravity research
> **Decision:** [D-021](../../DECISIONS.md#d-021) — ONNX-Unified Inference Pipeline

### ปัญหาที่พบ

สมมติฐานเดิมในส่วน 1 (`~900 MB ต่อ process`) **ผิด** — ประมาณการนั้นคิดราวกับว่า 3 โมเดลรันบน framework เดียว แต่ในความเป็นจริง:

| Framework | ใช้โดย | RAM overhead จริง |
|---|---|---|
| PyTorch | YOLOv8-nano | 400–600 MB |
| PaddlePaddle | PaddleOCR | 500–1,000 MB |
| ONNXRuntime | InsightFace | 200–300 MB |
| **รวม 3 frameworks** | — | **1,100–1,900 MB** 🔴 |

ที่ 1,900 MB + services ~350 MB = 2,250 MB → **OOM บน CPX11 (2 GB RAM)**

### การแก้ไข — D-021 ONNX-Unified

**แทน** preload pattern เดิมที่ใช้ 3 frameworks:
```python
# ❌ เดิม (Multi-framework — OOM risk)
yolo = YOLO("yolov8n.pt")           # โหลด PyTorch
ocr  = PaddleOCR(lang="en")         # โหลด PaddlePaddle
face = FaceAnalysis(name="buffalo_s") # โหลด ONNXRuntime
```

**ใช้** ONNX-unified แทน:
```python
# ✅ ใหม่ (ONNX-only — RAM ปลอดภัย)
import onnxruntime as ort

yolo_sess = ort.InferenceSession("models/yolov8n.onnx")   # ~200-400 MB
ocr_sess  = ort.InferenceSession("models/paddleocr.onnx") # ~150-300 MB
face_sess = ort.InferenceSession("models/buffalo_s/*.onnx") # ~200-300 MB
# รวม ≈ 500-800 MB → ปลอดภัยใต้ mem_limit: 1200m ✅
```

### RAM Budget ใหม่ (แก้ไขแล้ว)

| Service | RAM |
|---|---|
| Nginx | ~30 MB |
| FastAPI | ~150 MB |
| Redis | ~20 MB |
| **AI Worker (ONNX-unified)** | **~700 MB** (conservative) |
| vsftpd / kernel / overhead | ~150 MB |
| **รวม** | **~1,050 MB → เหลือ buffer ~950 MB ✅** |

### ONNX Export ก่อน Phase 3

สร้าง export scripts ใน `tools/export/` ก่อน Phase 3 เริ่ม:
- `tools/export/export_yolo.py` — `model.export(format='onnx', dynamic=True)`
- `tools/export/export_paddleocr.py` — `paddle2onnx` CLI wrapper
- InsightFace buffalo_s ไม่ต้อง export (เป็น ONNX อยู่แล้ว)
- ONNX model files → เก็บใน `models/` (gitignored) + download script
