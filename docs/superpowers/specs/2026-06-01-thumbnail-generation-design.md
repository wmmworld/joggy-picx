# Thumbnail Generation Design

**Date:** 2026-06-01
**Author:** Claude (Tech Lead)
**Status:** Approved

---

## Goal

Generate thumbnails (~30-60 KB JPEG) for every uploaded photo so the Photo Gallery loads fast. Currently rendering 14 × 6-7 MB originals makes the dashboard sluggish; we need ~100× smaller images for grid view.

The first real end-to-end smoke test (2026-06-01) exposed this — uploads work, but the dashboard takes seconds to render each card.

---

## Scope Decisions

- **When:** Deferred — generated in the RQ worker (`pipeline.py`), not during the `/ingest/photos` request. Ingest stays fast.
- **Where:** Worker downloads JPEG once for AI pipeline → resize before AI inference → upload thumbnail → continue with AI.
- **Resize spec:** 400×400 max bound, aspect-ratio preserved, JPEG quality 75.
- **Tool:** Pillow (`Pillow>=10.4`).
- **Failure mode:** Thumbnail errors log a warning but do not fail the AI pipeline. `Photo.r2_key_thumbnail` stays NULL — gallery falls back to original (current behaviour).

Out of scope:
- Backfilling thumbnails for the 15 photos already in the DB without thumbnails
- Multiple thumbnail sizes (small/medium/large)
- WebP / AVIF formats
- On-the-fly resize via Cloudflare Images
- Lazy-load attribute on `<img>` (frontend perf, separate concern)

---

## Architecture

Pillow resize happens in-memory between R2 download and the AI inference loop. One extra `r2.upload_bytes()` per photo. No new DB schema (`Photo.r2_key_thumbnail` column already exists).

```
process_photo(photo_id):
  ├─ db.get(Photo)
  ├─ event = db.get(Event)
  ├─ jpeg = r2.download_bytes(photo.r2_key_original)   ← existing
  │
  ├─ [NEW] thumb = generate_thumbnail(jpeg)
  ├─ [NEW] r2.upload_bytes(r2_key_thumbnail(...), thumb)
  ├─ [NEW] photo.r2_key_thumbnail = key
  │
  ├─ img = cv2.imdecode(jpeg)
  ├─ BibDetector → BibOcr → FaceEmbedder
  └─ DB writes + AuditLog (existing)
```

---

## Components

### `apps/backend/joggy/services/thumbnail.py` (new)

Single public function — pure (no I/O):

```python
def generate_thumbnail(jpeg_bytes: bytes, max_dim: int = 400, quality: int = 75) -> bytes:
    """Resize JPEG to fit within max_dim×max_dim, preserve aspect ratio.

    Returns JPEG bytes (~30-60KB for typical 6MB input).
    Raises ThumbnailError on decode failure (caller catches + skips).
    """
```

Implementation:
```python
from io import BytesIO
from PIL import Image, UnidentifiedImageError

class ThumbnailError(Exception):
    pass

def generate_thumbnail(jpeg_bytes: bytes, max_dim: int = 400, quality: int = 75) -> bytes:
    try:
        img = Image.open(BytesIO(jpeg_bytes))
        img.thumbnail((max_dim, max_dim))  # in-place, preserves aspect ratio
        out = BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except (UnidentifiedImageError, OSError) as e:
        raise ThumbnailError(f"Cannot decode/resize JPEG: {e}") from e
```

### `apps/backend/joggy/worker/pipeline.py` (modify)

After `r2.download_bytes(...)` and before `cv2.imdecode(...)`, insert:

```python
# Thumbnail generation (best-effort — failures don't break AI pipeline)
try:
    thumb_bytes = generate_thumbnail(img_bytes)
    thumb_key = r2.r2_key_thumbnail(str(photo.event_id), str(photo.id))
    r2.upload_bytes(thumb_key, thumb_bytes, content_type="image/jpeg")
    photo.r2_key_thumbnail = thumb_key
    logger.info("Thumbnail generated for %s (%d bytes)", photo.id, len(thumb_bytes))
except ThumbnailError as e:
    logger.warning("Thumbnail generation failed for %s: %s", photo.id, e)
```

`photo` is already loaded earlier in the function and saved via `db.add(photo)` at the existing UPDATE step — the new field flows through the same UPDATE.

### `apps/backend/pyproject.toml` (modify)

Add `"Pillow>=10.4.0,<12.0.0"` to dependencies.

---

## Data Flow

```
Daemon uploads original.jpg → R2
  ↓
POST /ingest/photos returns 202 + enqueues process_photo
  ↓
RQ worker: process_photo(photo_id)
  ↓
  1. Load Photo, Event from DB
  2. Download original.jpg from R2 (6 MB)
  3. Pillow.thumbnail(400×400) → JPEG 75% → ~50 KB
  4. Upload thumbnail.jpg → R2 at events/{event_id}/{photo_id}/thumbnail.jpg
  5. SET photo.r2_key_thumbnail = "events/.../thumbnail.jpg"
  6. AI pipeline (BibDetector, BibOcr, FaceEmbedder)
  7. UPDATE photos (bib_number, bib_confidence, ai_review_status, r2_key_thumbnail)
  ↓
Dashboard /events/{id}/photos endpoint:
  for each photo:
    key = photo.r2_key_thumbnail or photo.r2_key_original   ← existing fallback
    url = r2.signed_url(key, expires_in=3600)
  ↓
Frontend renders 50 KB thumbnails (instead of 6 MB originals)
```

The existing endpoint code in `apps/backend/joggy/api/internal.py` (lines around `r2_key_thumbnail or r2_key_original`) does not need to change — it already prefers thumbnail when available.

---

## Error Handling

| Failure | Behaviour |
|---------|-----------|
| Pillow `UnidentifiedImageError` (corrupt JPEG) | Log WARNING, skip thumbnail, continue AI pipeline. `r2_key_thumbnail` stays NULL. |
| R2 `upload_bytes` raises | Log ERROR, skip thumbnail, continue AI pipeline. |
| Out-of-memory (>50 MP image) | Log ERROR, skip. (Unlikely with Canon 26 MP RP.) |
| Backend running without Pillow | Import error at module load — caught by pytest in CI before deploy. |

Critical principle: **thumbnail is best-effort.** Original photo is the source of truth. Gallery already handles `r2_key_thumbnail = NULL` gracefully.

---

## Testing

### Unit tests — `tests/services/test_thumbnail.py`

1. **happy path** — small valid JPEG → output is JPEG bytes, smaller than input, max 400×400
2. **aspect ratio preserved** — 1920×1080 input → output max dim = 400, aspect ≈ 1.78
3. **portrait** — 1080×1920 input → output max dim = 400, aspect ≈ 0.56
4. **invalid bytes** — `b"not a jpeg"` → raises `ThumbnailError`
5. **already small** — 100×100 input → output ≤ input size (Pillow doesn't upscale)

Use Pillow itself to generate test JPEGs in fixtures (no static binary fixtures).

### Integration coverage

`test_pipeline.py` already mocks AI services + R2. Add 1 test:
- **thumbnail uploaded and key written** — mock `generate_thumbnail` + `r2.upload_bytes` → assert called with right key, `photo.r2_key_thumbnail` set
- **thumbnail failure doesn't break pipeline** — mock `generate_thumbnail` to raise `ThumbnailError` → pipeline still completes, `r2_key_thumbnail` stays None

---

## Out of Scope (Future Work)

- **Backfill** — 15 photos already uploaded without thumbnails. Manual script or background job to be done later if needed.
- **Frontend `loading="lazy"`** — independent perf win for grid; separate task.
- **Multiple sizes** — small/medium/large for different views; not needed yet.
- **WebP** — better compression but adds browser compat concerns; defer.
- **Cloudflare Image Resizing** — on-the-fly URL transform avoids storage but adds vendor cost; defer.
- **AI pipeline runs concurrently with R2 thumbnail upload** — sequential is fine at our scale (1,000 photos/event).

---

## Dependencies

New: `Pillow>=10.4.0,<12.0.0` — battle-tested, works on Windows/Linux ARM64, ~3 MB wheel.

Pillow already supports ARM64 wheels on PyPI, so Docker image build on Hetzner CPX11 (likely x86_64) and Pi 5 (ARM64) both work without compilation.
