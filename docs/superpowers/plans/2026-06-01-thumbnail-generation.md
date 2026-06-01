# Thumbnail Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate ~50 KB thumbnails for every uploaded photo so the Photo Gallery loads ~100× faster than serving 6 MB originals.

**Architecture:** Pillow resize inside the existing RQ worker `pipeline.py` — between R2 download and AI inference. Best-effort: thumbnail failure logs a warning but doesn't break the AI pipeline. Reuses `Photo.r2_key_thumbnail` column + `r2.r2_key_thumbnail()` helper (both already exist).

**Tech Stack:** Pillow 10.4+, existing FastAPI/SQLModel/asyncpg backend, existing pytest + pytest-asyncio test infra.

---

## File Map

**Create:**
- `apps/backend/joggy/services/thumbnail.py` — pure `generate_thumbnail()` function
- `apps/backend/tests/services/test_thumbnail.py` — 5 unit tests

**Modify:**
- `apps/backend/pyproject.toml` — add `Pillow>=10.4.0,<12.0.0`
- `apps/backend/joggy/worker/pipeline.py` — insert thumbnail step after JPEG download
- `apps/backend/tests/worker/test_pipeline.py` — add 2 integration tests

---

## Task 1: Add Pillow dependency

**Files:**
- Modify: `apps/backend/pyproject.toml`

- [ ] **Step 1: Read current `pyproject.toml`**

```bash
cat apps/backend/pyproject.toml
```

- [ ] **Step 2: Add Pillow to dependencies**

In `apps/backend/pyproject.toml`, add `"Pillow>=10.4.0,<12.0.0"` to the `dependencies` list (alphabetical order: after `pgvector`, before `pydantic-settings` — or just at the end of the list, ordering is style preference).

Resulting fragment should include this line:
```toml
  "Pillow>=10.4.0,<12.0.0",
```

- [ ] **Step 3: Sync deps**

```bash
cd apps/backend
uv sync
```

Expected: `Pillow` installed (~3 MB wheel).

- [ ] **Step 4: Verify import**

```bash
uv run python -c "from PIL import Image; print('Pillow', Image.__version__)"
```

Expected output: `Pillow 10.4.x` (or newer)

- [ ] **Step 5: Commit**

```bash
git add apps/backend/pyproject.toml uv.lock
git commit -m "feat(backend): add Pillow dependency for thumbnail generation

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: `thumbnail.py` service (TDD)

**Files:**
- Create: `apps/backend/joggy/services/thumbnail.py`
- Create: `apps/backend/tests/services/test_thumbnail.py`

`apps/backend/tests/services/__init__.py` already exists (from Phase 3 Task 1). If somehow missing, create as empty file before the test file.

- [ ] **Step 1: Write the failing tests**

Create `apps/backend/tests/services/test_thumbnail.py`:

```python
"""Tests for generate_thumbnail — pure JPEG resize via Pillow."""
import io

import pytest
from PIL import Image

from joggy.services.thumbnail import ThumbnailError, generate_thumbnail


def _make_jpeg(width: int, height: int, color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    """Helper: produce a valid JPEG of the requested size."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_landscape_resized_to_max_400():
    src = _make_jpeg(1920, 1080)
    out = generate_thumbnail(src)
    result = Image.open(io.BytesIO(out))
    assert result.format == "JPEG"
    assert max(result.size) == 400
    # Aspect ratio ≈ 1.78 (16:9)
    assert abs(result.size[0] / result.size[1] - 1920 / 1080) < 0.01


def test_portrait_resized_to_max_400():
    src = _make_jpeg(1080, 1920)
    out = generate_thumbnail(src)
    result = Image.open(io.BytesIO(out))
    assert max(result.size) == 400
    assert result.size[1] == 400  # tallest dimension
    # Aspect ratio ≈ 0.56
    assert abs(result.size[0] / result.size[1] - 1080 / 1920) < 0.01


def test_output_is_smaller_than_input():
    src = _make_jpeg(4000, 3000)
    out = generate_thumbnail(src)
    assert len(out) < len(src)
    # Sanity check on absolute size — typical 400×300 q75 JPEG ~5-30KB
    assert len(out) < 100 * 1024  # under 100 KB


def test_already_small_not_upscaled():
    src = _make_jpeg(100, 100)
    out = generate_thumbnail(src)
    result = Image.open(io.BytesIO(out))
    # Pillow's Image.thumbnail() never upscales
    assert max(result.size) == 100


def test_invalid_bytes_raises():
    with pytest.raises(ThumbnailError):
        generate_thumbnail(b"not a jpeg at all")
```

- [ ] **Step 2: Run to verify failure**

```bash
cd apps/backend
uv run pytest tests/services/test_thumbnail.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'joggy.services.thumbnail'`

- [ ] **Step 3: Implement `thumbnail.py`**

Create `apps/backend/joggy/services/thumbnail.py`:

```python
"""Thumbnail generation — pure in-memory JPEG resize via Pillow.

Used by the RQ worker (pipeline.py) to produce ~50KB previews of the
~6MB originals so the Photo Gallery loads quickly.

Best-effort: caller is expected to log + skip on ThumbnailError.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image, UnidentifiedImageError


class ThumbnailError(Exception):
    """Raised when the input cannot be decoded or resized."""


def generate_thumbnail(
    jpeg_bytes: bytes,
    max_dim: int = 400,
    quality: int = 75,
) -> bytes:
    """Resize JPEG to fit within `max_dim`x`max_dim`, preserve aspect ratio.

    Returns JPEG bytes (~30-60 KB for typical 6 MB camera input).
    Raises ThumbnailError on decode/resize failure.
    """
    try:
        img = Image.open(BytesIO(jpeg_bytes))
        img.thumbnail((max_dim, max_dim))  # in-place, preserves aspect ratio
        out = BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise ThumbnailError(f"Cannot decode/resize JPEG: {exc}") from exc
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
uv run pytest tests/services/test_thumbnail.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add apps/backend/joggy/services/thumbnail.py apps/backend/tests/services/test_thumbnail.py
git commit -m "feat(thumbnail): generate_thumbnail() — Pillow resize + 5 unit tests

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Wire thumbnail into pipeline.py

**Files:**
- Modify: `apps/backend/joggy/worker/pipeline.py`

- [ ] **Step 1: Read existing imports**

```bash
grep -n "^from\|^import" apps/backend/joggy/worker/pipeline.py | head -20
```

You should see imports like `from joggy.services import r2`, `import cv2`, etc.

- [ ] **Step 2: Add imports**

In `apps/backend/joggy/worker/pipeline.py`, add these imports near the top (with the other `joggy.services` imports):

```python
from joggy.services.thumbnail import ThumbnailError, generate_thumbnail
```

- [ ] **Step 3: Insert thumbnail step**

Find this existing block (around line 98–103):

```python
    # 2. Download + decode JPEG
    img_bytes = r2.download_bytes(photo.r2_key_original)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError(f"Cannot decode image for photo {photo_id}")
```

Insert the thumbnail step **immediately after** the `if img_bgr is None: raise` line and **before** `# 3. Bib detection`:

```python
    # 2.5 Thumbnail generation (best-effort — failures don't break AI pipeline)
    try:
        thumb_bytes = generate_thumbnail(img_bytes)
        thumb_key = r2.r2_key_thumbnail(str(photo.event_id), str(photo.id))
        r2.upload_bytes(thumb_key, thumb_bytes, content_type="image/jpeg")
        photo.r2_key_thumbnail = thumb_key
        logger.info(
            "Thumbnail generated for %s (%d bytes → %d bytes)",
            photo.id, len(img_bytes), len(thumb_bytes),
        )
    except ThumbnailError as e:
        logger.warning("Thumbnail generation failed for %s: %s", photo.id, e)
```

- [ ] **Step 4: Run existing tests to verify no regression**

```bash
cd apps/backend
uv run pytest tests/ -v 2>&1 | tail -10
```

Expected: 6 pipeline tests still pass (`tests/worker/test_pipeline.py`), all other tests pass. Total should be the same as before plus the 5 new thumbnail tests from Task 2.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/joggy/worker/pipeline.py
git commit -m "feat(pipeline): generate thumbnail before AI inference (best-effort)

Inserts thumbnail step between R2 download and bib detection. On
ThumbnailError, logs warning and continues — r2_key_thumbnail stays
NULL and Photo Gallery falls back to original via existing OR-fallback.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Pipeline integration tests for thumbnail

**Files:**
- Modify: `apps/backend/tests/worker/test_pipeline.py`

- [ ] **Step 1: Inspect existing test patches**

```bash
grep -n "patch(\"joggy.worker.pipeline" apps/backend/tests/worker/test_pipeline.py | head -10
```

The existing tests patch `joggy.worker.pipeline.r2.download_bytes`, `joggy.worker.pipeline.cv2.imdecode`, etc.

- [ ] **Step 2: Append 2 new tests**

Add these tests at the end of `apps/backend/tests/worker/test_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_thumbnail_uploaded_and_key_written(mock_db, photo, event):
    _setup_db_queries(mock_db, photo, event)
    sessions = _make_sessions()
    fake_img = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("joggy.worker.pipeline.r2.download_bytes", return_value=b"jpg"), \
         patch("joggy.worker.pipeline.cv2.imdecode", return_value=fake_img), \
         patch("joggy.worker.pipeline.generate_thumbnail", return_value=b"thumb-bytes") as mock_thumb, \
         patch("joggy.worker.pipeline.r2.upload_bytes") as mock_upload, \
         patch("joggy.worker.pipeline.BibDetector") as MockDet, \
         patch("joggy.worker.pipeline.BibOcr") as MockOcr, \
         patch("joggy.worker.pipeline.FaceEmbedder") as MockEmbed:

        MockDet.return_value.detect.return_value = None
        MockOcr.return_value.read.return_value = None
        MockEmbed.return_value.embed.return_value = None

        await run_pipeline(str(photo.id), mock_db, sessions)

    mock_thumb.assert_called_once_with(b"jpg")
    mock_upload.assert_called_once()
    upload_args = mock_upload.call_args
    # First positional arg is the R2 key
    thumb_key = upload_args.args[0]
    assert thumb_key.startswith(f"events/{photo.event_id}/")
    assert thumb_key.endswith("/thumbnail.jpg")
    assert photo.r2_key_thumbnail == thumb_key


@pytest.mark.asyncio
async def test_thumbnail_failure_does_not_break_pipeline(mock_db, photo, event):
    """ThumbnailError is caught, logged, pipeline continues. r2_key_thumbnail stays None."""
    from joggy.services.thumbnail import ThumbnailError

    _setup_db_queries(mock_db, photo, event)
    sessions = _make_sessions()
    fake_img = np.zeros((100, 100, 3), dtype=np.uint8)
    photo.r2_key_thumbnail = None  # baseline

    with patch("joggy.worker.pipeline.r2.download_bytes", return_value=b"jpg"), \
         patch("joggy.worker.pipeline.cv2.imdecode", return_value=fake_img), \
         patch("joggy.worker.pipeline.generate_thumbnail", side_effect=ThumbnailError("bad jpeg")), \
         patch("joggy.worker.pipeline.r2.upload_bytes") as mock_upload, \
         patch("joggy.worker.pipeline.BibDetector") as MockDet, \
         patch("joggy.worker.pipeline.BibOcr") as MockOcr, \
         patch("joggy.worker.pipeline.FaceEmbedder") as MockEmbed:

        MockDet.return_value.detect.return_value = None
        MockOcr.return_value.read.return_value = None
        MockEmbed.return_value.embed.return_value = None

        result = await run_pipeline(str(photo.id), mock_db, sessions)

    mock_upload.assert_not_called()
    assert photo.r2_key_thumbnail is None
    # Pipeline still completed and returned a summary
    assert result["photo_id"] == str(photo.id)
```

- [ ] **Step 3: Run pipeline tests — expect PASS**

```bash
cd apps/backend
uv run pytest tests/worker/test_pipeline.py -v
```

Expected: `8 passed` (6 existing + 2 new).

- [ ] **Step 4: Run full suite — no regressions**

```bash
uv run pytest tests/ -v 2>&1 | tail -5
```

Expected: all previous tests still pass, plus the 5 thumbnail tests from Task 2 and 2 new pipeline tests from this task.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/tests/worker/test_pipeline.py
git commit -m "test(pipeline): cover thumbnail happy path + ThumbnailError fallback

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Smoke test on Pi — capture a new photo and verify thumbnail

**Files:** None — this is a manual smoke test using the running Pi setup from earlier this session.

Prerequisites already met from the earlier smoke test:
- Backend running on laptop (`--host 0.0.0.0`)
- Pi edge daemon ready
- Event token in Pi `.env`
- Canon EOS RP on USB to Pi
- gphoto2 ready
- RQ worker has access to ONNX models or pipeline mocks the AI step (Phase 3 deferred — AI services will fail loudly without model files, see note below)

> **NOTE on RQ worker availability:** `process_photo` requires `_get_sessions()` to load ONNX model files which the project documents are NOT committed (D-021, bake-in-Docker). On a dev laptop without models, the worker will fail on session load. For this smoke test, run the thumbnail logic via direct `run_pipeline()` call from a Python REPL OR skip the AI pipeline by setting `MODEL_DIR` to a directory containing dummy ONNX files. If neither is feasible, the integration tests in Task 4 provide enough confidence — mark this task as DEFERRED and proceed to Task 6.

- [ ] **Step 1: Start RQ worker locally (if model files available)**

Skip if no model files. Otherwise:

```bash
cd apps/backend
uv run rq worker --url redis://localhost:6380/0 default
```

- [ ] **Step 2: Take a photo via gphoto2 on Pi**

In the Pi gphoto2 terminal (already running tethered mode):
- Press shutter once on the Canon

- [ ] **Step 3: Verify pipeline logs show thumbnail generated**

In the RQ worker terminal, expect a line like:
```
INFO ... Thumbnail generated for <photo_id> (~6,000,000 bytes → ~50,000 bytes)
```

- [ ] **Step 4: Verify Dashboard loads thumbnails fast**

Refresh `http://localhost:3000/dashboard/events/<event_id>/photos` — new photos should appear instantly (vs ~22s perceived load for 6 MB originals).

- [ ] **Step 5: Verify DB row**

In Supabase SQL Editor:
```sql
SELECT id, r2_key_original, r2_key_thumbnail
FROM photos
ORDER BY created_at DESC
LIMIT 5;
```

Expected: most recent row has `r2_key_thumbnail` populated (`events/.../thumbnail.jpg`); older rows have it NULL (no backfill in scope).

- [ ] **Step 6: Mark task complete**

No commit — this is verification only. Note actual thumbnail size in commit body of Task 6 if observed.

---

## Task 6: Update PROGRESS.md + CHANGELOG.md

**Files:**
- Modify: `PROGRESS.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update PROGRESS.md last-update header**

In `PROGRESS.md`, change:
```
วันที่อัปเดตล่าสุด: 2026-06-01
ผู้อัปเดตล่าสุด: Claude (Tech Lead) — Edge uploader (Pi → VPS) ✅ — inotify daemon, exponential retry, systemd service, 28 TDD tests
```
to:
```
วันที่อัปเดตล่าสุด: 2026-06-01
ผู้อัปเดตล่าสุด: Claude (Tech Lead) — Thumbnail generation ✅ — Pillow resize 400×400 in RQ worker, fast Photo Gallery loads
```

- [ ] **Step 2: Add bullet to Phase 4 milestones**

In `PROGRESS.md`, find the `### Phase 4 — Frontend + Integration` section and add a new line under it (after the edge uploader line):

```
- [x] **Thumbnail generation** ✅ — Pillow 400×400 q75 in pipeline.py (best-effort, ~100× smaller than originals)
```

- [ ] **Step 3: Add entry to CHANGELOG**

In `CHANGELOG.md`, under `## [Unreleased]` > `### Added`, prepend (at top of the Added list):

```
- [Claude] Thumbnail generation: `apps/backend/joggy/services/thumbnail.py` —
  pure `generate_thumbnail()` (Pillow 400×400 q75) + `ThumbnailError`. Wired
  into `pipeline.py` between R2 download and AI inference. Best-effort —
  failures log WARNING but don't break the AI pipeline. Photo Gallery
  already falls back to original when `r2_key_thumbnail` is NULL. Adds
  Pillow>=10.4 dep + 5 unit tests + 2 pipeline integration tests.
```

- [ ] **Step 4: Commit**

```bash
git add PROGRESS.md CHANGELOG.md
git commit -m "docs: update PROGRESS + CHANGELOG for thumbnail generation

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Done

After Task 6:
- `apps/backend/joggy/services/thumbnail.py` shipped with 5 passing unit tests
- `pipeline.py` integration verified with 2 new tests (8 pipeline tests total)
- Pillow added to dependencies
- PROGRESS + CHANGELOG updated
- Pi smoke test verified live (or deferred if no model files locally — integration tests sufficient)

Next photos uploaded via `joggy-edge` will get thumbnails. Existing 15 photos remain on the slow path until a future backfill task.
