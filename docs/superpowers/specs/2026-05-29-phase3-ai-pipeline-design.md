# Phase 3 — AI Pipeline Design

**Date:** 2026-05-29
**Author:** Claude (Tech Lead)
**Status:** Approved

---

## Goal

Implement the AI processing pipeline for `process_photo()` — the RQ worker task that runs for every ingested photo. The pipeline reads bib numbers via OCR, extracts face embeddings, and matches unrecognised photos to known runners via Cross-Checkpoint Re-ID, all using ONNX inference exclusively (D-021).

## Architecture

**Approach: Model service objects** — three independent service classes (`BibDetector`, `BibOcr`, `FaceEmbedder`), each wrapping its own ONNX session. A `pipeline.py` orchestrator calls them in order and handles all DB writes. Sessions are preloaded once at worker startup and passed via constructor.

**Why not a single function:** Three models are independently testable and may be updated at different cadences. Service boundaries make RAM usage per model visible and keep each file focused.

**Tech stack:** `onnxruntime` only — no `torch`, no `paddle` in production (D-021). Single worker process, models preloaded at boot (D-013).

---

## Model Storage

**Decision: Bake ONNX files into Docker image (C)**

Model files are copied into the worker Docker image at build time via `COPY models/ /app/models/`. No runtime downloads, no extra credentials, no startup delay. Models rarely change — a rebuild is acceptable when a model version is upgraded.

Export scripts in `tools/export/` are dev-only and never run in production.

| Model | Source | Size | Path in image |
|-------|--------|------|---------------|
| YOLOv8-nano bib | export_yolo.py (Ultralytics) | ~6 MB | `models/yolov8n_bib.onnx` |
| PaddleOCR det | export_ocr.py (paddle2onnx) | ~5 MB | `models/ocr_det.onnx` |
| PaddleOCR rec | export_ocr.py (paddle2onnx) | ~5 MB | `models/ocr_rec.onnx` |
| InsightFace det | download from InsightFace repo | ~5 MB | `models/buffalo_s/det_10g.onnx` |
| InsightFace embed | download from InsightFace repo | ~100 MB | `models/buffalo_s/w600k_r50.onnx` |

Total: ~121 MB added to worker image. `models/` is gitignored — populated via `make download-models` (or manual copy) before `docker build`.

---

## File Structure

```
apps/backend/
├── joggy/
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── session.py          # ONNX session loader — preload at worker boot
│   │   ├── bib_detector.py     # YOLOv8-nano → BibBox | None
│   │   ├── bib_ocr.py          # PaddleOCR → BibResult(number, confidence) | None
│   │   └── face_embedder.py    # InsightFace → FaceResult(vector[512]) | None
│   └── worker/
│       ├── pipeline.py         # orchestrator: AI services → DB writes → Re-ID
│       └── tasks.py            # process_photo() calls pipeline.run(photo_id)
│
├── models/                     # .gitignored — populated before docker build
│   ├── yolov8n_bib.onnx
│   ├── ocr_det.onnx
│   ├── ocr_rec.onnx
│   └── buffalo_s/
│       ├── det_10g.onnx
│       └── w600k_r50.onnx
│
└── tests/
    ├── ai/
    │   ├── __init__.py
    │   ├── test_bib_detector.py
    │   ├── test_bib_ocr.py
    │   └── test_face_embedder.py
    └── worker/
        └── test_pipeline.py    # already exists — expand with pipeline tests

tools/
└── export/
    ├── export_yolo.py          # dev-only: YOLOv8 → .onnx
    └── export_ocr.py           # dev-only: PaddleOCR → .onnx
```

---

## Service Interface

### `session.py` — Session Loader

```python
import onnxruntime as ort
from dataclasses import dataclass

@dataclass
class ModelSessions:
    yolo: ort.InferenceSession
    ocr_det: ort.InferenceSession
    ocr_rec: ort.InferenceSession
    face_det: ort.InferenceSession
    face_embed: ort.InferenceSession

def load_sessions(model_dir: str = "models") -> ModelSessions:
    """Call once at worker startup. Returns preloaded sessions."""
    return ModelSessions(
        yolo=ort.InferenceSession(f"{model_dir}/yolov8n_bib.onnx"),
        ocr_det=ort.InferenceSession(f"{model_dir}/ocr_det.onnx"),
        ocr_rec=ort.InferenceSession(f"{model_dir}/ocr_rec.onnx"),
        face_det=ort.InferenceSession(f"{model_dir}/buffalo_s/det_10g.onnx"),
        face_embed=ort.InferenceSession(f"{model_dir}/buffalo_s/w600k_r50.onnx"),
    )
```

### `bib_detector.py`

```python
from dataclasses import dataclass
import numpy as np
import onnxruntime as ort

@dataclass
class BibBox:
    x1: int; y1: int; x2: int; y2: int
    confidence: float

class BibDetector:
    def __init__(self, session: ort.InferenceSession) -> None:
        self._sess = session

    def detect(self, img_bgr: np.ndarray) -> BibBox | None:
        """Run YOLOv8-nano. Return highest-confidence bib box, or None."""
        # preprocess → run → postprocess (NMS) → return BibBox | None
```

### `bib_ocr.py`

```python
@dataclass
class BibResult:
    number: str        # e.g. "1234"
    confidence: float  # 0.0–1.0

class BibOcr:
    def __init__(self, det_sess: ort.InferenceSession, rec_sess: ort.InferenceSession) -> None: ...

    def read(self, img_bgr: np.ndarray, bbox: BibBox) -> BibResult | None:
        """Crop bib region → PaddleOCR det+rec → BibResult | None."""
```

### `face_embedder.py`

```python
@dataclass
class FaceResult:
    vector: np.ndarray  # shape (512,), L2-normalised

class FaceEmbedder:
    def __init__(self, det_sess: ort.InferenceSession, embed_sess: ort.InferenceSession) -> None: ...

    def embed(self, img_bgr: np.ndarray) -> FaceResult | None:
        """Detect face → align → extract 512-dim L2-normalised embedding, or None."""
```

---

## Pipeline Orchestration (`pipeline.py`)

```
Input: photo_id (str)

1.  Load Photo row from DB → get r2_key
2.  Download JPEG bytes from R2 → decode to numpy BGR
3.  BibDetector.detect(img)    → bbox | None
4.  BibOcr.read(img, bbox)     → BibResult(number, confidence) | None
5.  FaceEmbedder.embed(img)    → FaceResult(vector) | None
6.  Determine ai_review_status:
      confidence >= 0.70 AND bib_number is not None → 'auto'
      otherwise                                     → 'low_confidence' or 'no_bib'
7.  UPDATE photos SET
        bib_number, bib_confidence, ai_review_status = 'auto' | 'pending'
8.  If face_vector:
        INSERT face_embeddings (photo_id, vector, created_at)
9.  If bib_number is None AND face_vector:
        Re-ID: query face_embeddings WHERE photo.event_id = this event
               cosine_similarity(face_vector, candidate) > 0.85
               → take highest-scoring match's bib_number
               → UPDATE photos SET bib_number, ai_review_status='auto'
               → skip INSERT into review_queue
10. If bib_number still None OR confidence < 0.70:
        INSERT review_queue (photo_id, reason='no_bib'|'low_confidence')
11. AuditLog: action='ai_pipeline_complete', metadata={bib,confidence,reid}
```

### `ai_review_status` values

| Value | Meaning |
|-------|---------|
| `pending` | ยังไม่ process |
| `auto` | AI อ่านได้ confidence ≥ 0.70 (หรือ Re-ID match) |
| `reviewed` | Staff approve/reject แล้วใน dashboard |
| `failed` | Pipeline error — ดู AuditLog |

---

## Cross-Checkpoint Re-ID

**Scope:** Same event only (same `event_id`). ไม่ match ข้าม event หรือ organizer

**Algorithm:**
```sql
SELECT fe.photo_id, fe.vector, p.bib_number
FROM face_embeddings fe
JOIN photos p ON p.id = fe.photo_id
WHERE p.event_id = :event_id
  AND p.bib_number IS NOT NULL
ORDER BY (fe.vector <=> :query_vector)   -- pgvector cosine distance
LIMIT 5
```
จาก top-5 candidates เลือก candidate ที่ `1 - distance > 0.85` และ score สูงสุด

**ถ้าไม่มี match:** รูปคงอยู่ใน review_queue ต่อไป — staff review ด้วยตนเอง

---

## Error Handling

| กรณี | พฤติกรรม |
|------|-----------|
| R2 download fail | raise → RQ retry max 3 ครั้ง, exponential backoff 60s/300s/900s |
| ONNX inference error | catch → mark `ai_review_status='failed'` + INSERT review_queue(reason='error') + AuditLog |
| ไม่เจอ bib เลย | bib_number=None, confidence=0.0 → review_queue(reason='no_bib') |
| ไม่เจอหน้าเลย | face_vector=None → ข้าม Re-ID, pipeline ดำเนินต่อตามปกติ |
| Re-ID ไม่เจอ match | รูปอยู่ใน review_queue ต่อ |
| DB write fail | raise → RQ retry, idempotent (UPDATE ใช้ photo_id เป็น PK) |
| models/ ไม่มีไฟล์ | worker fail at startup, ไม่รับ job — ต้องแก้ Docker image |

---

## Testing Approach (TDD)

**`tests/ai/test_bib_detector.py`**
- Mock `ort.InferenceSession` → inject fake output tensors
- Test: detect returns BibBox เมื่อ YOLO output confidence สูง
- Test: detect returns None เมื่อ no detection / confidence ต่ำกว่า 0.5

**`tests/ai/test_bib_ocr.py`**
- Mock det + rec sessions
- Test: read returns BibResult(number="1234", confidence=0.85)
- Test: read returns None เมื่อ rec output ว่าง

**`tests/ai/test_face_embedder.py`**
- Mock det + embed sessions
- Test: embed returns FaceResult(vector) shape (512,) L2-normalised
- Test: embed returns None เมื่อ no face detected

**`tests/worker/test_pipeline.py`**
- Mock BibDetector, BibOcr, FaceEmbedder, R2 download, DB session
- Test: happy path → photos updated, face_embeddings inserted, no review_queue
- Test: low_confidence → review_queue inserted, ai_review_status='pending'
- Test: no_bib + face → Re-ID query executed
- Test: reid_match → bib_number updated, review_queue NOT inserted
- Test: ONNX error → status='failed', review_queue inserted

---

## Export Scripts (Dev Only)

**`tools/export/export_yolo.py`**
```python
# Requires: pip install ultralytics (dev env only)
from ultralytics import YOLO
model = YOLO("yolov8n.pt")  # or fine-tuned weights
model.export(format="onnx", imgsz=640, simplify=True)
# Output: yolov8n.onnx → copy to models/yolov8n_bib.onnx
```

**`tools/export/export_ocr.py`**
```python
# Requires: pip install paddle2onnx paddlepaddle (dev env only)
# paddle2onnx --model_dir ch_PP-OCRv4_det_infer --save_file models/ocr_det.onnx
# paddle2onnx --model_dir ch_PP-OCRv4_rec_infer --save_file models/ocr_rec.onnx
```

**InsightFace buffalo_s:** ดาวน์โหลดจาก `https://github.com/deepinsight/insightface` โดยตรง — ไฟล์เป็น ONNX อยู่แล้ว ไม่ต้อง export

---

## Out of Scope (Phase 3)

- Manual Review Queue UI — Cursor (frontend task, separate spec)
- Gender detection — defer to Phase 4 (ไม่ได้ใช้ใน MVP)
- PDPA auto-delete cron — Phase 4
- Thumbnail generation — Phase 4
- Model fine-tuning บน Thai bib dataset — post-MVP

---

## Decisions Referenced

- **D-004** CPU-only AI inference
- **D-013** Single RQ worker process, model preload at boot
- **D-021** ONNX-only inference engine (no torch/paddle in production)
- **D-014** face_embeddings retention 7 days
- **D-003** pgvector for face similarity search
